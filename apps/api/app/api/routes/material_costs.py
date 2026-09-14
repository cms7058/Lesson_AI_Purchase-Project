import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.persistence import (
    ComparisonSnapshotRecord,
    CostAdjustmentRecord,
    GoodsReceiptRecord,
    PurchaseOrderLineRecord,
    PurchaseOrderRecord,
    PurchaseReturnRecord,
    QualityInspectionRecord,
    QuotationLineRecord,
    QuotationRecord,
)
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/material-costs", tags=["material-costs"])
ZERO = Decimal(0)


class CostInput(BaseModel):
    model_config = ConfigDict(validate_default=True, str_strip_whitespace=True)
    logistics: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    rework: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    delay: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    other: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    credit: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    basis: str = Field(default="estimated", pattern="^(actual|estimated)$")
    evidence: str = Field(min_length=2, max_length=1000)


def histories(db: Session, code: str, currency: str) -> dict:
    orders = list(db.scalars(select(PurchaseOrderRecord).join(PurchaseOrderLineRecord)
        .where(PurchaseOrderLineRecord.material_code == code, PurchaseOrderRecord.currency == currency)
        .options(selectinload(PurchaseOrderRecord.lines)).order_by(PurchaseOrderRecord.created_at.desc())).unique())
    order_map = {order.id: order for order in orders}
    order_rows = []
    for order in orders:
        for line in order.lines:
            if line.material_code != code:
                continue
            order_rows.append({"id": line.id, "order_id": order.id, "order_no": order.order_no,
                "supplier_id": order.supplier_id, "supplier_name": order.supplier_name,
                "date": order.created_at, "currency": order.currency, "status": order.status,
                "quantity": line.quantity, "unit_price": line.unit_price, "unit": line.unit,
                "amount": line.quantity * line.unit_price * (1 + line.tax_rate), "delivery_date": line.delivery_date})
    quotations = list(db.scalars(select(QuotationRecord).join(QuotationLineRecord)
        .where(QuotationLineRecord.material_code == code, QuotationRecord.currency == currency)
        .options(selectinload(QuotationRecord.lines)).order_by(QuotationRecord.created_at.desc())).unique())
    quote_rows = []
    for quote in quotations:
        for line in quote.lines:
            if line.material_code == code:
                quote_rows.append({"id": line.id, "quotation_no": quote.quotation_no, "supplier_id": quote.supplier_id,
                    "supplier_name": quote.supplier_name, "date": quote.created_at, "quantity": line.quantity,
                    "unit": line.unit, "unit_price": line.unit_price, "currency": quote.currency,
                    "delivery_days": quote.delivery_days, "quality_pass_rate": quote.quality_pass_rate,
                    "tco": line.quantity * line.unit_price * (1 + line.tax_rate) + line.logistics_cost + line.expected_quality_loss})
    receipt_records = list(db.scalars(select(GoodsReceiptRecord).where(GoodsReceiptRecord.material_code == code,
        GoodsReceiptRecord.order_id.in_(list(order_map))).order_by(GoodsReceiptRecord.created_at.desc())))
    ids = [r.id for r in receipt_records]
    adjustments = {a.receipt_id: a for a in db.scalars(select(CostAdjustmentRecord).where(CostAdjustmentRecord.receipt_id.in_(ids)))}
    inspections = {i.receipt_id: i for i in db.scalars(select(QualityInspectionRecord).where(QualityInspectionRecord.receipt_id.in_(ids)))}
    returns = {}
    for item in db.scalars(select(PurchaseReturnRecord).where(PurchaseReturnRecord.receipt_id.in_(ids), PurchaseReturnRecord.status != "draft")):
        returns[item.receipt_id] = returns.get(item.receipt_id, ZERO) + item.quantity
    receipt_rows = []
    for receipt in receipt_records:
        order = order_map[receipt.order_id]
        lines = [line for line in order.lines if line.material_code == code]
        prices = {(line.unit_price, line.tax_rate, line.unit) for line in lines}
        unambiguous = len(prices) == 1
        unit_price = lines[0].unit_price * (1 + lines[0].tax_rate) if unambiguous else None
        adjustment = adjustments.get(receipt.id)
        inspection = inspections.get(receipt.id)
        complete = inspection is not None and inspection.inspected_quantity == receipt.received_quantity
        base = unit_price * receipt.received_quantity if unit_price is not None else None
        values = {key: getattr(adjustment, key) if adjustment else ZERO for key in ["logistics", "rework", "delay", "other", "credit"]}
        corrected = base + values["logistics"] + values["rework"] + values["delay"] + values["other"] - values["credit"] if base is not None else None
        eligible = receipt.status == "inspected" and complete and corrected is not None
        due_dates = {line.delivery_date for line in lines}
        due = next(iter(due_dates)) if len(due_dates) == 1 else None
        late_days = max(0, (receipt.received_date - due).days) if due and receipt.received_date else None
        receipt_rows.append({"id": receipt.id, "receipt_no": receipt.receipt_no, "order_no": order.order_no,
            "supplier_id": order.supplier_id, "supplier_name": order.supplier_name, "currency": currency,
            "date": receipt.received_date or receipt.created_at.date(), "status": receipt.status,
            "received_quantity": receipt.received_quantity, "accepted_quantity": receipt.accepted_quantity,
            "rejected_quantity": receipt.rejected_quantity, "rework_quantity": inspection.rework_quantity if inspection else None,
            "returned_quantity": returns.get(receipt.id, ZERO), "late_days": late_days,
            "unit": lines[0].unit if unambiguous else "混合单位", "base_amount": base, "base_unit_cost": unit_price,
            "corrected_amount": corrected if eligible else None,
            "corrected_unit_cost": corrected / receipt.accepted_quantity if eligible and receipt.accepted_quantity > 0 else None,
            "eligible": eligible, "note": "订单同物料有不同价格或单位，无法确定批次成本" if not unambiguous else ("未完成全批质检，不参与成本修正" if not eligible else "以订单价格计价，不等同财务已结算成本"),
            "basis": adjustment.basis if adjustment else "unconfirmed", "evidence": adjustment.evidence if adjustment else "未补充费用凭证，附加费用暂按0计算",
            **values})
    snapshots = [{"id": s.id, "date": s.created_at, "quantity": s.quantity, "currency": s.currency,
        "result": json.loads(s.result_json), "created_by": s.created_by} for s in db.scalars(select(ComparisonSnapshotRecord)
        .where(ComparisonSnapshotRecord.material_code == code, ComparisonSnapshotRecord.currency == currency)
        .order_by(ComparisonSnapshotRecord.created_at.desc()))]
    return {"orders": order_rows, "quotations": quote_rows, "receipts": receipt_rows, "comparisons": snapshots}


@router.get("/summary")
def summary(material_code: str = Query(min_length=1, max_length=64), currency: str = Query(default="CNY", min_length=3, max_length=3), db: Session = Depends(get_db)):
    data = histories(db, material_code, currency)
    groups = {}
    for row in data["receipts"]:
        key = (row["supplier_id"], row["unit"])
        group = groups.setdefault(key, {"supplier_id": row["supplier_id"], "supplier_name": row["supplier_name"], "unit": row["unit"], "currency": currency,
            "batches": 0, "eligible_batches": 0, "received": ZERO, "accepted": ZERO, "rejected": ZERO,
            "base_amount": ZERO, "corrected_amount": ZERO, "eligible_received": ZERO, "eligible_accepted": ZERO, "confirmed_batches": 0})
        group["batches"] += 1
        if row["status"] != "draft":
            group["received"] += row["received_quantity"]
            group["accepted"] += row["accepted_quantity"]
            group["rejected"] += row["rejected_quantity"]
        if row["eligible"]:
            group["eligible_batches"] += 1
            group["base_amount"] += row["base_amount"]
            group["corrected_amount"] += row["corrected_amount"]
            group["eligible_received"] += row["received_quantity"]
            group["eligible_accepted"] += row["accepted_quantity"]
            group["confirmed_batches"] += int(row["basis"] == "actual")
    for group in groups.values():
        group["base_unit_cost"] = group["base_amount"] / group["eligible_received"] if group["eligible_received"] else None
        group["corrected_unit_cost"] = group["corrected_amount"] / group["eligible_accepted"] if group["eligible_accepted"] else None
        inspected = group["accepted"] + group["rejected"]
        group["quality_rate"] = group["accepted"] / inspected * 100 if inspected else None
    supplier_options = {row["supplier_id"]: row["supplier_name"] for key in ("orders", "quotations", "receipts") for row in data[key]}
    return {"material_code": material_code, "currency": currency, "supplier_options": [{"id": key, "name": value} for key, value in supplier_options.items()], "counts": {key: len(rows) for key, rows in data.items()},
        "suppliers": list(groups.values()), "formula": "修正TOC＝按订单含税价计价的收货货款＋物流＋返工＋延期＋其他－退款/索赔；单位合格品成本＝修正TOC÷合格数量。同币种、同单位比较，未完成全批质检或价格不明确的批次不纳入。"}


@router.get("/history/{kind}")
def history(kind: str, material_code: str = Query(min_length=1,max_length=64), currency: str = "CNY", supplier_id: str = "", page: int = Query(1,ge=1), page_size: int = Query(10,ge=1,le=100), db: Session = Depends(get_db)):
    if kind not in {"orders", "quotations", "receipts", "comparisons"}:
        raise HTTPException(status_code=404, detail="未知历史类型")
    rows = histories(db, material_code, currency)[kind]
    if supplier_id and kind != "comparisons":
        rows = [row for row in rows if row["supplier_id"] == supplier_id]
    return {"items": rows[(page-1)*page_size:page*page_size], "total": len(rows), "page": page, "page_size": page_size}


@router.put("/receipts/{receipt_id}/adjustment")
def adjust(receipt_id: str, payload: CostInput, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    if user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=403, detail="仅采购经理或管理员可修正成本")
    receipt = db.get(GoodsReceiptRecord, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="未找到收货记录")
    order = db.get(PurchaseOrderRecord, receipt.order_id)
    if order is None:
        raise HTTPException(status_code=409, detail="关联订单不存在")
    row = next(r for r in histories(db, receipt.material_code, order.currency)["receipts"] if r["id"] == receipt_id)
    if not row["eligible"]:
        raise HTTPException(status_code=409, detail=row["note"])
    values = payload.model_dump()
    if payload.credit > row["base_amount"] + payload.logistics + payload.rework + payload.delay + payload.other:
        raise HTTPException(status_code=422, detail="退款/索赔不能超过总成本")
    record = db.scalar(select(CostAdjustmentRecord).where(CostAdjustmentRecord.receipt_id == receipt_id))
    if record is None:
        record = CostAdjustmentRecord(receipt_id=receipt_id, created_by=user.user_id, **values)
        db.add(record)
    else:
        for key, value in values.items():
            setattr(record, key, value)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="adjust", resource_type="receipt_cost",resource_id=receipt_id,detail=json.dumps(values,default=str,ensure_ascii=False))
    db.commit()
    return {"saved": True}


@router.delete("/receipts/{receipt_id}/adjustment", status_code=204)
def remove_adjustment(receipt_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    if user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=403, detail="无权清除成本修正")
    record = db.scalar(select(CostAdjustmentRecord).where(CostAdjustmentRecord.receipt_id == receipt_id))
    if record is None:
        raise HTTPException(status_code=404, detail="未找到成本修正")
    db.delete(record)
    write_audit_log(db,actor_id=user.user_id,actor_role=user.role,action="delete",resource_type="receipt_cost",resource_id=receipt_id,detail="清除成本修正，恢复未确认附加费用状态")
    db.commit()
