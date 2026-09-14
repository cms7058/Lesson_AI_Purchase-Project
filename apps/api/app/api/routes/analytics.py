from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, require_roles
from app.domain.order_buyer import OrderBuyerAssignment
from app.domain.persistence import (
    MaterialCategoryAssignmentRecord,
    MaterialCategoryRecord,
    MaterialRecord,
    PurchaseOrderLineRecord,
    PurchaseOrderRecord,
    StaffUserRecord,
    SupplierRecord,
)
from app.services.audit_service import write_audit_log
from app.services.supply_analysis import metric_groups

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/cockpit")
def cockpit_analytics(db: Session = Depends(get_db), currency: str = Query("CNY", min_length=3, max_length=3), start: date | None = None, end: date | None = None, status: str = "", supplier: str = "", buyer: str = "", page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    from app.services.cockpit import cockpit
    return cockpit(db, currency, start, end, status, supplier, page, page_size, buyer)


class BuyerAssignmentInput(BaseModel):
    buyer_id: str | None = None


@router.put("/order-buyers/{order_id}")
def assign_buyer(order_id: str, payload: BuyerAssignmentInput, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER))):
    order = db.get(PurchaseOrderRecord, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    existing = db.get(OrderBuyerAssignment, order_id)
    if payload.buyer_id:
        buyer = db.get(StaffUserRecord, payload.buyer_id)
        if not buyer or buyer.status != "active" or buyer.role not in {"buyer", "procurement_manager"}:
            raise HTTPException(422, "请选择启用的采购员或采购经理")
        if existing:
            existing.buyer_id = buyer.id
            existing.assigned_by = user.user_id
        else:
            db.add(OrderBuyerAssignment(order_id=order_id, buyer_id=buyer.id, assigned_by=user.user_id))
    elif existing:
        db.delete(existing)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="assign_buyer", resource_type="purchase_order", resource_id=order_id, detail=f"订单 {order.order_no} 指定采购员 {payload.buyer_id or '未分配'}")
    db.commit()
    return {"order_id": order_id, "buyer_id": payload.buyer_id}


@router.get("/procurement")
def procurement_analytics(db: Session = Depends(get_db)) -> dict:
    order_total = db.scalar(select(func.count()).select_from(PurchaseOrderRecord)) or 0
    supplier_total = db.scalar(select(func.count()).select_from(SupplierRecord)) or 0
    material_total = db.scalar(select(func.count()).select_from(MaterialRecord)) or 0
    high_risk = db.scalar(
        select(func.count()).select_from(SupplierRecord).where(SupplierRecord.risk_level == "high")
    ) or 0
    amount = db.scalar(
        select(func.coalesce(func.sum(PurchaseOrderLineRecord.quantity * PurchaseOrderLineRecord.unit_price), 0))
    ) or 0

    order_status = [
        {"name": status, "value": count}
        for status, count in db.execute(
            select(PurchaseOrderRecord.status, func.count())
            .group_by(PurchaseOrderRecord.status)
            .order_by(PurchaseOrderRecord.status)
        )
    ]
    supplier_risk = [
        {"name": risk, "value": count}
        for risk, count in db.execute(
            select(SupplierRecord.risk_level, func.count())
            .group_by(SupplierRecord.risk_level)
            .order_by(SupplierRecord.risk_level)
        )
    ]
    supplier_performance = [{"name": row["supplier_name"]+" / "+row["material_code"], "quality": row["metrics"]["quality"]["median"], "delivery": row["metrics"]["delivery"]["median"], "response_hours": row["metrics"]["response"]["median"]} for row in metric_groups(db)[:8]]
    supplier_amount = [
        {"name": name, "value": float(value or 0)}
        for name, value in db.execute(
            select(
                PurchaseOrderRecord.supplier_name,
                func.sum(PurchaseOrderLineRecord.quantity * PurchaseOrderLineRecord.unit_price),
            )
            .join(PurchaseOrderLineRecord, PurchaseOrderLineRecord.order_id == PurchaseOrderRecord.id)
            .group_by(PurchaseOrderRecord.supplier_name)
            .order_by(func.sum(PurchaseOrderLineRecord.quantity * PurchaseOrderLineRecord.unit_price).desc())
            .limit(8)
        )
    ]
    category_distribution = [
        {"name": path, "value": count}
        for path, count in db.execute(
            select(MaterialCategoryRecord.path_name, func.count(MaterialCategoryAssignmentRecord.id))
            .outerjoin(
                MaterialCategoryAssignmentRecord,
                MaterialCategoryAssignmentRecord.category_id == MaterialCategoryRecord.id,
            )
            .where(MaterialCategoryRecord.level == 3)
            .group_by(MaterialCategoryRecord.id, MaterialCategoryRecord.path_name)
            .order_by(MaterialCategoryRecord.code)
        )
    ]
    return {
        "kpis": {
            "order_count": order_total,
            "purchase_amount": float(amount),
            "supplier_count": supplier_total,
            "high_risk_supplier_count": high_risk,
            "material_count": material_total,
        },
        "order_status": order_status,
        "supplier_risk": supplier_risk,
        "supplier_performance": supplier_performance,
        "supplier_amount": supplier_amount,
        "category_distribution": category_distribution,
    }
