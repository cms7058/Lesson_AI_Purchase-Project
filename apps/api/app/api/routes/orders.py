from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.orders import PurchaseOrder, PurchaseOrderCreate, PurchaseOrderUpdate
from app.domain.persistence import (
    GoodsReceiptRecord,
    PurchaseOrderRecord,
    PurchaseReturnRecord,
    QualityInspectionRecord,
)
from app.services.audit_service import write_audit_log
from app.services.order_service import order_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}/trace")
def order_trace(order_id: str, kind: str = "receipts", page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    order = db.get(PurchaseOrderRecord, order_id)
    if order is None:
        raise HTTPException(404, "未找到订单")
    models = {"receipts": GoodsReceiptRecord, "inspections": QualityInspectionRecord, "returns": PurchaseReturnRecord}
    if kind not in models:
        raise HTTPException(422, "不支持的追溯类型")
    model = models[kind]
    receipt_ids = select(GoodsReceiptRecord.id).where(GoodsReceiptRecord.order_id == order_id)
    condition = model.order_id == order_id if kind == "receipts" else model.receipt_id.in_(receipt_ids)
    total = db.scalar(select(func.count()).select_from(model).where(condition)) or 0
    ordering = model.inspected_at if kind == "inspections" else model.created_at
    rows = db.scalars(select(model).where(condition).order_by(ordering.desc(), model.id).offset((page-1)*page_size).limit(page_size))
    return {"order_no": order.order_no, "status": order.status, "items": [jsonable_encoder({c.name: getattr(r, c.name) for c in model.__table__.columns}) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("", response_model=Page[PurchaseOrder])
def list_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[PurchaseOrder]:
    items, total = order_service.list_orders(db, page, page_size)
    return Page(items=list(items), page=page, page_size=page_size, total=total)


@router.post("", response_model=PurchaseOrder, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PurchaseOrder:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权创建采购订单")
    order = order_service.create_order(db, payload, current_user.user_id)
    write_audit_log(
        db,
        actor_id=current_user.user_id,
        actor_role=current_user.role,
        action="create",
        resource_type="purchase_order",
        resource_id=str(order.id),
        detail=f"创建订单 {order.order_no}",
    )
    db.commit()
    return order


@router.patch("/{order_id}", response_model=PurchaseOrder)
def update_order(
    order_id: str,
    payload: PurchaseOrderUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PurchaseOrder:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权修改采购订单")
    order = order_service.update_order(db, order_id, payload)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到采购订单")
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="update", resource_type="purchase_order", resource_id=order_id, detail=f"更新订单 {order.order_no}")
    db.commit()
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权删除采购订单")
    if not order_service.delete_order(db, order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到采购订单")
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="delete", resource_type="purchase_order", resource_id=order_id, detail="删除采购订单")
    db.commit()
