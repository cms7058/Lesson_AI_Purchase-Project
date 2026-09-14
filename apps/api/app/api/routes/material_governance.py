import re
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.material_governance import MaterialDuplicateDecisionRecord
from app.domain.persistence import MaterialRecord
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/material-governance", tags=["material-governance"])
MANAGERS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}


class DecisionIn(BaseModel):
    left_material_id: str
    right_material_id: str
    similarity: float = Field(ge=0, le=1)
    status: str = Field(pattern="^(watchlist|duplicate|not_duplicate)$")
    master_material_id: str = ""
    basis: list[str] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=1000)


def normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (value or "").lower())


def ratio(left: str, right: str) -> float:
    a, b = normalized(left), normalized(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def compare(left: MaterialRecord, right: MaterialRecord) -> tuple[float, list[str]]:
    name = ratio(left.name, right.name)
    specification = ratio(left.specification, right.specification)
    category = ratio(left.category, right.category)
    unit = 1.0 if normalized(left.unit) and normalized(left.unit) == normalized(right.unit) else 0.0
    score = name * 0.5 + specification * 0.35 + category * 0.1 + unit * 0.05
    basis = [f"名称相似度 {name:.0%}", f"规格相似度 {specification:.0%}"]
    if category >= 0.8:
        basis.append("分类接近")
    if unit:
        basis.append("计量单位一致")
    return round(score, 4), basis


def pair_ids(left_id: str, right_id: str) -> tuple[str, str]:
    if left_id == right_id:
        raise HTTPException(422, "不能比较同一物料")
    return tuple(sorted((left_id, right_id)))


@router.get("/duplicates")
def duplicates(
    threshold: float = Query(0.65, ge=0.4, le=1),
    keyword: str = Query("", max_length=100),
    decision_status: str = Query("all", pattern="^(all|unreviewed|watchlist|duplicate|not_duplicate)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query = select(MaterialRecord).where(MaterialRecord.active.is_(True)).order_by(MaterialRecord.code).limit(1001)
    materials = list(db.scalars(query))
    truncated = len(materials) > 1000
    materials = materials[:1000]
    if keyword:
        key = keyword.lower().strip()
        candidate_ids = {m.id for m in materials if key in f"{m.code} {m.name} {m.specification}".lower()}
    else:
        candidate_ids = set()
    decisions = {(r.left_material_id, r.right_material_id): r for r in db.scalars(select(MaterialDuplicateDecisionRecord))}
    rows = []
    for index, left in enumerate(materials):
        for right in materials[index + 1:]:
            if candidate_ids and left.id not in candidate_ids and right.id not in candidate_ids:
                continue
            score, basis = compare(left, right)
            pair = pair_ids(left.id, right.id)
            decision = decisions.get(pair)
            row_status = decision.status if decision else "unreviewed"
            if score < threshold and not decision:
                continue
            if decision_status != "all" and row_status != decision_status:
                continue
            rows.append({
                "left": {"id": left.id, "code": left.code, "name": left.name, "specification": left.specification, "category": left.category, "unit": left.unit},
                "right": {"id": right.id, "code": right.code, "name": right.name, "specification": right.specification, "category": right.category, "unit": right.unit},
                "similarity": score,
                "basis": basis,
                "status": row_status,
                "master_material_id": decision.master_material_id if decision else "",
                "note": decision.note if decision else "",
                "decided_by": decision.decided_by if decision else "",
                "decided_at": decision.decided_at if decision else None,
            })
    rows.sort(key=lambda item: (item["status"] != "unreviewed", -item["similarity"], item["left"]["code"]))
    total = len(rows)
    start = (page - 1) * page_size
    return {"items": rows[start:start + page_size], "total": total, "page": page, "page_size": page_size, "threshold": threshold, "truncated": truncated}


@router.post("/duplicate-decisions")
def decide(payload: DecisionIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    if user.role not in MANAGERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "当前角色无权确认重复料")
    left_id, right_id = pair_ids(payload.left_material_id, payload.right_material_id)
    left, right = db.get(MaterialRecord, left_id), db.get(MaterialRecord, right_id)
    if not left or not right:
        raise HTTPException(404, "物料不存在")
    if payload.status == "duplicate" and payload.master_material_id not in {left_id, right_id}:
        raise HTTPException(422, "确认重复时必须指定其中一个物料为主物料")
    record = db.scalar(select(MaterialDuplicateDecisionRecord).where(
        MaterialDuplicateDecisionRecord.left_material_id == left_id,
        MaterialDuplicateDecisionRecord.right_material_id == right_id,
    ))
    if not record:
        record = MaterialDuplicateDecisionRecord(left_material_id=left_id, right_material_id=right_id)
        db.add(record)
    record.similarity = payload.similarity
    record.status = payload.status
    record.master_material_id = payload.master_material_id if payload.status == "duplicate" else ""
    record.basis = "；".join(payload.basis)
    record.note = payload.note
    record.decided_by = user.user_id
    db.flush()
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="review", resource_type="material_duplicate", resource_id=record.id, detail=f"{left.code}/{right.code} → {payload.status}")
    db.commit(); db.refresh(record)
    return {"id": record.id, "status": record.status, "master_material_id": record.master_material_id, "decided_by": record.decided_by, "decided_at": record.decided_at}
