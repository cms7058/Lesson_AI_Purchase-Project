from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from app.domain.order_buyer import OrderBuyerAssignment
from app.domain.persistence import PurchaseOrderLineRecord as Line
from app.domain.persistence import PurchaseOrderRecord as Order
from app.services.buyer_analytics import buyer_statistics
from app.services.category_analytics import category_analytics
from app.services.list_filters import STATUS_LABELS


def cockpit(db, currency, start, end, status, supplier, page, page_size, buyer=""):
    if start and end and start > end:
        raise HTTPException(422, "开始日期不能晚于结束日期")
    clauses = [Order.currency == currency, Order.status != "cancelled"]
    if start:
        clauses.append(Order.created_at >= start)
    if end:
        clauses.append(Order.created_at < end + timedelta(days=1))
    if status:
        clauses.append(Order.status == status)
    if supplier:
        clauses.append(Order.supplier_name == supplier)
    if buyer:
        clauses.append(OrderBuyerAssignment.buyer_id.is_(None) if buyer == "unassigned" else OrderBuyerAssignment.buyer_id == buyer)
    amounts = select(Line.order_id, func.sum(Line.quantity * Line.unit_price).label("amount")).group_by(Line.order_id).subquery()
    base = select(Order.id, Order.order_no, Order.status, Order.supplier_name, Order.created_at, OrderBuyerAssignment.buyer_id, func.coalesce(amounts.c.amount, 0).label("amount")).outerjoin(amounts, amounts.c.order_id == Order.id).outerjoin(OrderBuyerAssignment, OrderBuyerAssignment.order_id == Order.id).where(*clauses).subquery()
    total, amount, suppliers = db.execute(select(func.count(), func.coalesce(func.sum(base.c.amount), 0), func.count(func.distinct(base.c.supplier_name)))).one()
    def grouped(column, aggregate, descending=False):
        statement = select(column, aggregate).select_from(base).group_by(column).order_by(aggregate.desc() if descending else column)
        return [{"name": name, "value": float(value)} for name, value in db.execute(statement)]
    statuses = grouped(base.c.status, func.count())
    for item in statuses:
        item["code"] = item["name"]
        item["name"] = STATUS_LABELS.get(item["name"], item["name"])
    rows = [dict(row) for row in db.execute(select(base).order_by(base.c.created_at.desc(), base.c.id).offset((page-1)*page_size).limit(page_size)).mappings()]
    for row in rows:
        row["status"] = STATUS_LABELS.get(row["status"], row["status"])
    currencies = list(db.scalars(select(Order.currency).distinct().order_by(Order.currency)))
    buyer_stats, delivery_stats = buyer_statistics(db, base)
    buyer_names = {b["key"]: b["name"] for b in buyer_stats}
    month = func.substr(base.c.created_at, 1, 7)
    buyer_timeline = [{"month": period, "buyer_id": key or "unassigned", "buyer_name": buyer_names.get(key or "unassigned", "未分配采购员"), "amount": float(value)} for period, key, value in db.execute(select(month, base.c.buyer_id, func.sum(base.c.amount)).group_by(month, base.c.buyer_id).order_by(month, base.c.buyer_id))]
    material_amount = [{"name": code, "value": float(value)} for code, value in db.execute(select(Line.material_code, func.sum(Line.quantity * Line.unit_price)).join(base, base.c.id == Line.order_id).group_by(Line.material_code).order_by(func.sum(Line.quantity * Line.unit_price).desc(), Line.material_code))]
    for row in rows:
        row["buyer_name"] = buyer_names.get(row["buyer_id"] or "unassigned", "未分配采购员")
    extra = {"buyer_timeline": buyer_timeline, "material_amount": material_amount, "category_amount": category_analytics(db, base)}
    return {**extra, "buyer_stats": buyer_stats, "buyer_supplier_delivery": delivery_stats, "currency": currency, "currencies": sorted(set(currencies + ["CNY"])), "as_of": datetime.now(UTC).date().isoformat(), "kpis": {"order_count": total, "purchase_amount": float(amount), "supplier_count": suppliers, "completed_count": db.scalar(select(func.count()).select_from(base).where(base.c.status == "completed")) or 0}, "order_status": statuses, "supplier_amount": grouped(base.c.supplier_name, func.sum(base.c.amount), True)[:8], "trend": grouped(func.substr(base.c.created_at, 1, 7), func.sum(base.c.amount)), "rows": rows, "total": total, "page": page, "page_size": page_size}
