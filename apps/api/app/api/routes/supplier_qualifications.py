import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.persistence import SupplierRecord
from app.domain.supplier_qualifications import (
    QualificationDecision,
    QualificationInput,
    QualificationView,
    SupplierQualificationRecord,
    SupplierQualificationRevision,
)
from app.services.audit_service import write_audit_log

router = APIRouter(tags=["supplier-qualifications"])
MANAGERS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}
FILES = Path("private_supplier_qualifications")


def require_manager(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in MANAGERS:
        raise HTTPException(403, "只有系统管理员或采购经理可以维护供应商资质")
    return user


def get_record(db: Session, item_id: str) -> SupplierQualificationRecord:
    item = db.get(SupplierQualificationRecord, item_id)
    if not item:
        raise HTTPException(404, "未找到供应商资质")
    return item


def effective(item: SupplierQualificationRecord) -> tuple[str, int | None]:
    remaining = (item.expires_on - datetime.now(UTC).date()).days if item.expires_on else None
    if item.review_status in {"rejected", "suspended"}:
        return item.review_status, remaining
    if item.review_status != "approved":
        return "pending", remaining
    if remaining is not None and remaining < 0:
        return "expired", remaining
    if remaining is not None and remaining <= 30:
        return "expiring", remaining
    return "valid", remaining


def view(db: Session, item: SupplierQualificationRecord) -> QualificationView:
    supplier = db.get(SupplierRecord, item.supplier_id)
    state, remaining = effective(item)
    return QualificationView.model_validate(item).model_copy(update={
        "supplier_code": supplier.code if supplier else "",
        "supplier_name": supplier.name if supplier else "已删除供应商",
        "effective_status": state,
        "days_to_expiry": remaining,
    })


def snapshot(item: SupplierQualificationRecord) -> dict:
    return {key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in {
        "qualification_type": item.qualification_type,
        "certificate_no": item.certificate_no,
        "issuing_authority": item.issuing_authority,
        "valid_from": item.valid_from,
        "expires_on": item.expires_on,
        "review_status": item.review_status,
        "review_note": item.review_note,
        "attachment_name": item.attachment_name,
    }.items()}


def revision(db: Session, item: SupplierQualificationRecord, action: str, actor: str) -> None:
    db.add(SupplierQualificationRevision(qualification_id=item.id, version=item.version, action=action, snapshot_json=json.dumps(snapshot(item), ensure_ascii=False), actor_id=actor))


def audit(db: Session, user: CurrentUser, action: str, item: SupplierQualificationRecord, detail: str) -> None:
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action=action, resource_type="supplier_qualification", resource_id=item.id, detail=detail)


@router.get("/supplier-qualifications")
def list_qualifications(
    supplier_id: str = "",
    keyword: str = Query("", max_length=100),
    effective_status: str = Query("", pattern="^(|pending|valid|expiring|expired|rejected|suspended)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = []
    if supplier_id:
        filters.append(SupplierQualificationRecord.supplier_id == supplier_id)
    if keyword:
        term = f"%{keyword.strip()}%"
        supplier_ids = select(SupplierRecord.id).where(or_(SupplierRecord.code.ilike(term), SupplierRecord.name.ilike(term)))
        filters.append(or_(SupplierQualificationRecord.qualification_type.ilike(term), SupplierQualificationRecord.certificate_no.ilike(term), SupplierQualificationRecord.issuing_authority.ilike(term), SupplierQualificationRecord.supplier_id.in_(supplier_ids)))
    records = list(db.scalars(select(SupplierQualificationRecord).where(*filters).order_by(SupplierQualificationRecord.expires_on, SupplierQualificationRecord.created_at.desc())))
    rows = [view(db, item) for item in records]
    counts = {key: sum(item.effective_status == key for item in rows) for key in ("pending", "valid", "expiring", "expired", "rejected", "suspended")}
    if effective_status:
        rows = [item for item in rows if item.effective_status == effective_status]
    start = (page - 1) * page_size
    return {"items": rows[start:start + page_size], "total": len(rows), "page": page, "page_size": page_size, "counts": counts}


@router.post("/suppliers/{supplier_id}/qualifications", response_model=QualificationView, status_code=201)
def create_qualification(supplier_id: str, payload: QualificationInput, db: Session = Depends(get_db), user: CurrentUser = Depends(require_manager)):
    if not db.get(SupplierRecord, supplier_id):
        raise HTTPException(404, "未找到供应商")
    item = SupplierQualificationRecord(supplier_id=supplier_id, **payload.model_dump(), review_status="pending", created_by=user.user_id)
    db.add(item); db.flush(); revision(db, item, "create", user.user_id)
    audit(db, user, "create", item, f"新增供应商资质 {item.qualification_type}")
    db.commit(); db.refresh(item)
    return view(db, item)


@router.patch("/supplier-qualifications/{item_id}", response_model=QualificationView)
def update_qualification(item_id: str, payload: QualificationInput, db: Session = Depends(get_db), user: CurrentUser = Depends(require_manager)):
    item = get_record(db, item_id)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.version += 1
    item.review_status = "pending"
    item.reviewed_by = ""; item.reviewed_at = None
    db.flush(); revision(db, item, "update", user.user_id)
    audit(db, user, "update", item, f"更新供应商资质至V{item.version}，重新进入待审核")
    db.commit(); db.refresh(item)
    return view(db, item)


@router.post("/supplier-qualifications/{item_id}/decision", response_model=QualificationView)
def decide_qualification(item_id: str, payload: QualificationDecision, db: Session = Depends(get_db), user: CurrentUser = Depends(require_manager)):
    item = get_record(db, item_id)
    if payload.status == "rejected" and not payload.note.strip():
        raise HTTPException(422, "驳回资质必须填写原因")
    if payload.status == "approved" and not item.attachment_path:
        raise HTTPException(409, "请先上传资质证明文件，再审核通过")
    item.review_status = payload.status
    item.review_note = payload.note.strip()
    item.reviewed_by = user.user_id
    item.reviewed_at = datetime.now(UTC)
    db.flush(); revision(db, item, "review", user.user_id)
    audit(db, user, "review", item, f"资质审核：{payload.status}")
    db.commit(); db.refresh(item)
    return view(db, item)


@router.post("/supplier-qualifications/{item_id}/attachment", response_model=QualificationView)
async def upload_attachment(item_id: str, file: UploadFile = File(...), db: Session = Depends(get_db), user: CurrentUser = Depends(require_manager)):
    item = get_record(db, item_id)
    name = Path((file.filename or "qualification").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(422, "资质附件仅支持PDF、Word、Excel和图片")
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(422, "资质附件须为1字节至10MB")
    FILES.mkdir(exist_ok=True)
    old_path = FILES / item.attachment_path if item.attachment_path else None
    storage = uuid4().hex + suffix
    (FILES / storage).write_bytes(content)
    item.attachment_name, item.attachment_path = name[:240], storage
    item.version += 1
    item.review_status = "pending"
    item.reviewed_by = ""; item.reviewed_at = None
    db.flush(); revision(db, item, "attachment", user.user_id)
    audit(db, user, "upload", item, f"上传资质附件并更新至V{item.version}")
    db.commit(); db.refresh(item)
    if old_path and old_path.is_file():
        old_path.unlink()
    return view(db, item)


@router.get("/supplier-qualifications/{item_id}/attachment")
def download_attachment(item_id: str, db: Session = Depends(get_db)):
    item = get_record(db, item_id)
    path = FILES / item.attachment_path if item.attachment_path else None
    if not path or not path.is_file():
        raise HTTPException(404, "资质附件不存在")
    return FileResponse(path, filename=item.attachment_name, media_type="application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})


@router.get("/supplier-qualifications/{item_id}/history")
def qualification_history(item_id: str, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    get_record(db, item_id)
    total = db.scalar(select(func.count()).select_from(SupplierQualificationRevision).where(SupplierQualificationRevision.qualification_id == item_id)) or 0
    rows = db.scalars(select(SupplierQualificationRevision).where(SupplierQualificationRevision.qualification_id == item_id).order_by(SupplierQualificationRevision.created_at.desc(), SupplierQualificationRevision.version.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [{"id": row.id, "version": row.version, "action": row.action, "snapshot": json.loads(row.snapshot_json), "actor_id": row.actor_id, "created_at": row.created_at} for row in rows], "total": total, "page": page, "page_size": page_size}


@router.delete("/supplier-qualifications/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_qualification(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(require_manager)):
    item = get_record(db, item_id)
    path = FILES / item.attachment_path if item.attachment_path else None
    audit(db, user, "delete", item, f"删除供应商资质 {item.qualification_type}")
    for row in db.scalars(select(SupplierQualificationRevision).where(SupplierQualificationRevision.qualification_id == item.id)):
        db.delete(row)
    db.delete(item); db.commit()
    if path and path.is_file():
        path.unlink()
