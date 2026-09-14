import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.rfqs import RFQ, RFQAward, RFQCreate, RFQResponseLink, RFQUpdate
from app.domain.supplier_portal import MailSettings
from app.domain.supply_feedback import AwardAnalysisSnapshot
from app.services.audit_service import write_audit_log
from app.services.rfq_mail import dispatch_rfq, queue_invitations
from app.services.rfq_service import rfq_service
from app.services.supply_analysis import rfq_analysis

router = APIRouter(prefix="/rfqs", tags=["rfqs"])
EDITORS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}


def _require(user: CurrentUser) -> None:
    if user.role not in EDITORS:
        raise HTTPException(status_code=403, detail="当前角色无权管理询价项目")


def _error(reason: str | None) -> None:
    messages = {"not_found": (404, "未找到询价项目或报价"), "locked": (409, "已发布的询价项目不能修改或删除"), "invalid_status": (409, "当前状态不允许此操作"), "not_invited": (409, "该报价供应商未被邀请"), "response_missing": (409, "该报价尚未关联到询价项目")}
    if reason:
        code, detail = messages[reason]
        raise HTTPException(status_code=code, detail=detail)


def _audit(db: Session, user: CurrentUser, action: str, item_id: str, detail: str) -> None:
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action=action, resource_type="rfq_project", resource_id=item_id, detail=detail)


@router.get("", response_model=Page[RFQ])
def list_rfqs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = Query("", max_length=100), status_filter: str = Query("", alias="status"), db: Session = Depends(get_db)) -> Page[RFQ]:
    items, total = rfq_service.list(db, page, page_size, keyword, status_filter)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post("", response_model=RFQ, status_code=status.HTTP_201_CREATED)
def create_rfq(payload: RFQCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> RFQ:
    _require(user); item = rfq_service.create(db, payload, user.user_id); _audit(db, user, "create", str(item.id), f"创建询价项目 {item.rfq_no}"); db.commit(); return item


@router.patch("/{item_id}", response_model=RFQ)
def update_rfq(item_id: str, payload: RFQUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> RFQ:
    _require(user); item, reason = rfq_service.update(db, item_id, payload); _error(reason); assert item is not None; _audit(db, user, "update", item_id, f"更新询价项目 {item.rfq_no}"); db.commit(); return item


@router.post("/{item_id}/publish", response_model=RFQ)
def publish_rfq(item_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> RFQ:
    _require(user)
    item, reason = rfq_service.publish(db, item_id)
    _error(reason)
    assert item is not None
    _audit(db, user, "publish", item_id, f"发布询价项目 {item.rfq_no}")
    queue_invitations(db, rfq_service.get(db, item_id))
    settings = db.get(MailSettings, 1)
    auto_send = bool(settings and settings.auto_send)
    db.commit()
    if auto_send:
        tasks.add_task(dispatch_rfq, item_id)
    return item


@router.post("/{item_id}/responses", response_model=RFQ, deprecated=True)
def link_response(item_id: str, payload: RFQResponseLink, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> RFQ:
    _require(user); item, reason = rfq_service.link_response(db, item_id, str(payload.quotation_id)); _error(reason); assert item is not None; _audit(db, user, "link_response", item_id, f"关联供应商报价 {payload.quotation_id}"); db.commit(); return item


@router.post("/{item_id}/award", response_model=RFQ)
def award_rfq(item_id: str, payload: RFQAward, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> RFQ:
    _require(user)
    if user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=403, detail="当前角色无权定标")
    analysis = rfq_analysis(db, item_id, include_demo=False)
    eligible = analysis["lowest_ids"] if payload.method == "lowest" else analysis["tco_ids"]
    if str(payload.quotation_id) not in eligible:
        raise HTTPException(409, "所选报价未核验、不是当前分析的最优有效报价，或历史成本数据不足，请刷新分析")
    item, reason = rfq_service.award(db, item_id, str(payload.quotation_id))
    _error(reason)
    assert item is not None
    db.add(AwardAnalysisSnapshot(rfq_id=item_id, quotation_id=str(payload.quotation_id), method=payload.method, result_json=json.dumps(analysis, ensure_ascii=False)))
    _audit(db, user, "award", item_id, f"{payload.method}定标报价 {payload.quotation_id}")
    db.commit()
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rfq(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    _require(user); deleted, reason = rfq_service.delete(db, item_id); _error(reason); assert deleted; _audit(db, user, "delete", item_id, "删除询价项目"); db.commit()
