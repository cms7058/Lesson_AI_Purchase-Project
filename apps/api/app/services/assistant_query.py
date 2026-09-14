"""Read-only, allowlisted queries. Model output is never executed as SQL."""
import json
import re
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select

from app.domain import persistence as p
from app.services.list_filters import (
    LABELS,
    SPECS,
    STATUS_LABELS,
    criteria_for,
    field_type,
    fields_for,
)

RESOURCES = {
    "orders": ("订单", "采购单"), "rfqs": ("询价",),
    "suppliers": ("供应商",), "materials": ("物料",),
    "quotations": ("价格", "报价", "比价"),
    "staff-users": ("人员", "员工", "采购员"),
    "buyer-authorizations": ("权限", "授权"),
}


def infer_resource(message):
    message = message.replace("查询", "") if "询价单" not in message else message
    for resource in ("buyer-authorizations", "staff-users", "orders", "rfqs", "quotations", "suppliers", "materials"):
        if any(word in message for word in RESOURCES[resource]):
            return resource
    return None


def infer_filters(resource, message):
    fields = fields_for(resource)
    filters = []
    def add(field, op, value):
        if field in fields:
            filters.append({"field": field, "op": op, "value": value})
    if "status" in fields:
        for code, label in sorted(STATUS_LABELS.items(), key=lambda item: -len(item[1])):
            if label in message:
                add("status", "eq", code)
                break
    for label, field in [("物料编码", "material_code" if resource != "materials" else "code"), ("物料编号", "material_code" if resource != "materials" else "code"), ("订单号", "order_no"), ("询价编号", "rfq_no"), ("供应商名称", "supplier_name" if resource != "suppliers" else "name"), ("人员编码", "user_code"), ("部门", "department"), ("币种", "currency")]:
        match = re.search(label + r"[：:\s]*[\"“]?([^\s，,。\"”]+)", message)
        if match:
            add(field, "eq", match.group(1))
    codes = re.findall(r"\b[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9-]+\b", message)
    if codes and not filters:
        key = {"orders": "order_no", "rfqs": "rfq_no", "quotations": "material_code", "suppliers": "code", "materials": "code", "staff-users": "user_code"}.get(resource)
        add(key, "eq", codes[0])
    if "本月" in message:
        add("created_at", "gte", datetime.now(UTC).date().replace(day=1).isoformat())
        add("created_at", "lte", (datetime.now(UTC).date()+timedelta(days=1)).isoformat())
    match = re.search(r"近(\d{1,3})天", message)
    if match:
        add("created_at", "gte", (datetime.now(UTC).date()-timedelta(days=int(match.group(1)))).isoformat())
    return filters


def query_data(db, payload, role, supplier=None):
    resource = payload.resource or infer_resource(payload.message)
    if not resource:
        return None
    if resource not in RESOURCES:
        raise HTTPException(422, "不支持的助手查询资源")
    if resource in {"staff-users", "buyer-authorizations"} and role not in {"admin", "procurement_manager"}:
        raise HTTPException(403, "人员与权限查询仅向系统管理员和采购经理开放")
    query_resource = "supplier/" + resource if supplier is not None and resource in {"orders", "rfqs"} else resource
    filters = payload.filters if payload.filters is not None else infer_filters(query_resource, payload.message)
    model, title, names = SPECS[resource]
    condition = criteria_for(query_resource, json.dumps(filters))
    criteria = [condition] if condition is not None else []
    if supplier is not None:
        if resource == "orders":
            criteria.extend([model.supplier_id.in_([supplier.id, supplier.code]), model.status.in_(["sent", "supplier_confirmed", "partially_delivered", "quality_tracking", "completed"])])
        elif resource == "rfqs":
            criteria.extend([model.invitations.any(p.RFQInvitationRecord.supplier_id.in_([supplier.id, supplier.code])), model.status.in_(["published", "awarded", "closed"])])
        else:
            raise HTTPException(403, "供应商助手仅可查询本企业订单和受邀询价")
    query = select(model).where(*criteria)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.order_by(model.created_at.desc(), model.id).offset((payload.page-1)*payload.page_size).limit(payload.page_size)).all()
    names = [name for name in names.split() if name in model.__table__.columns]
    rows = [{name: getattr(record, name) for name in names} for record in records]
    group = "role" if resource == "staff-users" else "risk_level" if resource == "suppliers" else "category" if resource == "materials" else "status" if hasattr(model, "status") else "currency"
    column = getattr(model, group)
    distribution = [{"name": STATUS_LABELS.get(name, name) or "未分类", "value": count} for name, count in db.execute(select(column, func.count()).where(*criteria).group_by(column).order_by(func.count().desc()).limit(20))]
    columns = [{"key": name, "label": LABELS.get(name, name)} for name in names]
    if resource == "quotations":
        # Per-page line details preserve currency, unit and tax; never average incompatible prices.
        rows = [{**row, "明细": "；".join(f"{line.material_code} {line.material_name}: {line.unit_price} {record.currency}/{line.unit}，数量{line.quantity}，税率{line.tax_rate}" for line in record.lines)} for row, record in zip(rows, records, strict=True)]
        columns.append({"key": "明细", "label": "报价单价明细（税前）"})
    if resource == "buyer-authorizations":
        for row in rows:
            buyer = db.get(p.StaffUserRecord, row["buyer_id"])
            category = db.get(p.MaterialCategoryRecord, row["category_id"])
            row["buyer_id"] = f"{buyer.user_code} / {buyer.name}" if buyer else row["buyer_id"]
            row["category_id"] = f"{category.code} / {category.path_name}" if category else row["category_id"]
    for row in rows:
        if "status" in row:
            row["status"] = STATUS_LABELS.get(row["status"], row["status"])
    available_fields = [{"key": name, "label": LABELS.get(name, name), "type": field_type(column)} for name, column in fields_for(query_resource).items()]
    return jsonable_encoder({"resource": resource, "title": title, "filters": filters, "available_fields": available_fields, "columns": columns, "rows": rows, "total": total, "page": payload.page, "page_size": payload.page_size, "chart": {"title": f"{title} · {LABELS.get(group, group)}分布（全部匹配记录，前20组）", "data": distribution}})
