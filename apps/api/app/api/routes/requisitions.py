from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.orders import PurchaseOrder
from app.domain.requisitions import (
    ApprovalDecision,
    Requisition,
    RequisitionConversion,
    RequisitionCreate,
    RequisitionUpdate,
)
from app.services.audit_service import write_audit_log
from app.services.requisition_service import requisition_service

router = APIRouter(prefix="/requisitions", tags=["requisitions"])
EDITORS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}
APPROVERS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}


def _require(user: CurrentUser, roles: set[UserRole], message: str) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail=message)


def _error(reason: str | None) -> None:
    if reason == "not_found":
        raise HTTPException(status_code=404, detail="未找到采购申请")
    if reason == "locked":
        raise HTTPException(status_code=409, detail="当前状态不允许修改或删除")
    if reason == "invalid_status":
        raise HTTPException(status_code=409, detail="当前状态不允许执行此操作")


def _audit(db: Session, user: CurrentUser, action: str, item_id: str, detail: str) -> None:
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action=action, resource_type="purchase_requisition", resource_id=item_id, detail=detail)


@router.get("", response_model=Page[Requisition])
def list_requisitions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = Query("", max_length=100), status_filter: str = Query("", alias="status"), db: Session = Depends(get_db)) -> Page[Requisition]:
    items, total = requisition_service.list(db, page, page_size, keyword, status_filter)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post("", response_model=Requisition, status_code=status.HTTP_201_CREATED)
def create_requisition(payload: RequisitionCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Requisition:
    _require(user, EDITORS, "当前角色无权创建采购申请")
    item = requisition_service.create(db, payload, user.user_id)
    _audit(db, user, "create", str(item.id), f"创建采购申请 {item.request_no}")
    db.commit()
    return item


@router.patch("/{item_id}", response_model=Requisition)
def update_requisition(item_id: str, payload: RequisitionUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Requisition:
    _require(user, EDITORS, "当前角色无权修改采购申请")
    item, reason = requisition_service.update(db, item_id, payload)
    _error(reason)
    assert item is not None
    _audit(db, user, "update", item_id, f"更新采购申请 {item.request_no}")
    db.commit()
    return item


@router.post("/{item_id}/submit", response_model=Requisition)
def submit_requisition(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Requisition:
    _require(user, EDITORS, "当前角色无权提交采购申请")
    item, reason = requisition_service.submit(db, item_id)
    _error(reason)
    assert item is not None
    _audit(db, user, "submit", item_id, f"提交采购申请 {item.request_no} 审批")
    db.commit()
    return item


@router.post("/{item_id}/decision", response_model=Requisition)
def decide_requisition(item_id: str, payload: ApprovalDecision, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Requisition:
    _require(user, APPROVERS, "当前角色无权审批采购申请")
    item, reason = requisition_service.decide(db, item_id, payload.approved, payload.comment, user.user_id)
    _error(reason)
    assert item is not None
    action = "approve" if payload.approved else "reject"
    _audit(db, user, action, item_id, f"{'批准' if payload.approved else '驳回'}采购申请 {item.request_no}")
    db.commit()
    return item


@router.post("/{item_id}/convert-to-order", response_model=PurchaseOrder, status_code=status.HTTP_201_CREATED)
def convert_to_order(item_id: str, payload: RequisitionConversion, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> PurchaseOrder:
    _require(user, EDITORS, "当前角色无权生成采购订单")
    order, reason = requisition_service.convert(db, item_id, payload, user.user_id)
    _error(reason)
    assert order is not None
    _audit(db, user, "convert", item_id, f"采购申请转订单 {order.order_no}")
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="create", resource_type="purchase_order", resource_id=str(order.id), detail=f"由采购申请 {item_id} 生成订单 {order.order_no}")
    db.commit()
    return order


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requisition(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    _require(user, EDITORS, "当前角色无权删除采购申请")
    deleted, reason = requisition_service.delete(db, item_id)
    _error(reason)
    if not deleted:
        raise HTTPException(status_code=404, detail="未找到采购申请")
    _audit(db, user, "delete", item_id, "删除采购申请")
    db.commit()
