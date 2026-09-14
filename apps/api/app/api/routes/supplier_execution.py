from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.routes.fulfillment import _receipt_capacity
from app.api.routes.supplier_portal import editor, supplier_user
from app.core.database import get_db
from app.domain.persistence import (
    GoodsReceiptRecord,
    PaymentRecord,
    PurchaseOrderRecord,
    ReconciliationRecord,
    SupplierInvoiceRecord,
    SupplierRecord,
)
from app.domain.supplier_execution import SupplierDelivery, SupplierInvoiceFile
from app.services.audit_service import write_audit_log
from app.services.numbering import next_sequence
from app.services.order_service import _to_domain

router = APIRouter(tags=["supplier-execution"])
FILES = Path("private_supplier_invoices")
VISIBLE = {"sent", "supplier_confirmed", "partially_delivered", "quality_tracking", "completed"}


def ownership(db, account):
    supplier = db.get(SupplierRecord, account.supplier_id)
    return PurchaseOrderRecord.supplier_id.in_([supplier.id, supplier.code])


def owned_order(db, account, order_id):
    order = db.scalar(select(PurchaseOrderRecord).where(PurchaseOrderRecord.id == order_id, ownership(db, account), PurchaseOrderRecord.status.in_(VISIBLE)))
    if not order:
        raise HTTPException(404, "未找到已发送给您的采购订单")
    return order


def page_result(db, query, page, page_size, convert):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.offset((page-1)*page_size).limit(page_size))
    return {"items": [convert(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def audit(db, account, action, kind, item_id, detail):
    write_audit_log(db, actor_id="supplier:"+account.id, actor_role="supplier", action=action, resource_type=kind, resource_id=item_id, detail=detail)


@router.get("/supplier/orders")
def orders(account=Depends(supplier_user), db=Depends(get_db), page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    query = select(PurchaseOrderRecord).where(ownership(db, account), PurchaseOrderRecord.status.in_(VISIBLE)).order_by(PurchaseOrderRecord.created_at.desc(), PurchaseOrderRecord.id)
    return page_result(db, query, page, page_size, lambda r: _to_domain(r).model_dump(mode="json"))


@router.post("/supplier/orders/{order_id}/confirm")
def confirm_order(order_id: str, account=Depends(supplier_user), db=Depends(get_db)):
    owned_order(db, account, order_id)
    result = db.execute(update(PurchaseOrderRecord).where(PurchaseOrderRecord.id == order_id, PurchaseOrderRecord.status == "sent").values(status="supplier_confirmed"))
    if result.rowcount != 1:
        raise HTTPException(409, "订单已确认或状态已变化，请刷新")
    audit(db, account, "confirm", "purchase_order", order_id, "供应商确认接单")
    db.commit()
    return {"status": "supplier_confirmed"}


class DeliveryInput(BaseModel):
    order_id: str
    material_code: str = Field(min_length=1, max_length=64)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    carrier: str = Field(min_length=1, max_length=120)
    tracking_no: str = Field(min_length=1, max_length=120)
    shipped_date: date
    expected_date: date

    @model_validator(mode="after")
    def dates(self):
        if self.expected_date < self.shipped_date:
            raise ValueError("预计到货日期不能早于发货日期")
        return self


def delivery_dict(db, row):
    receipt = db.get(GoodsReceiptRecord, row.receipt_id)
    return {**jsonable_encoder({c.name: getattr(row, c.name) for c in row.__table__.columns}), "order_no": receipt.order_no, "supplier_name": receipt.supplier_name, "material_code": receipt.material_code, "material_name": receipt.material_name, "quantity": str(receipt.received_quantity), "receipt_no": receipt.receipt_no, "status": "in_transit" if receipt.status == "draft" else receipt.status}


@router.post("/supplier/deliveries", status_code=201)
def dispatch(payload: DeliveryInput, account=Depends(supplier_user), db=Depends(get_db)):
    order = owned_order(db, account, payload.order_id)
    if order.status not in {"supplier_confirmed", "partially_delivered", "quality_tracking"}:
        raise HTTPException(409, "请先确认接单；完成的订单不能再次交付")
    # Serialize capacity checks on this order, including multiple concurrent shipments.
    locked = db.execute(update(PurchaseOrderRecord).where(PurchaseOrderRecord.id == order.id, PurchaseOrderRecord.status.in_({"supplier_confirmed", "partially_delivered", "quality_tracking"})).values(status=PurchaseOrderRecord.status))
    if locked.rowcount != 1:
        raise HTTPException(409, "订单状态已变化，请刷新后重试")
    line = next((l for l in order.lines if l.material_code == payload.material_code), None)
    if not line:
        raise HTTPException(422, "物料不属于该采购订单")
    _receipt_capacity(db, order, payload.material_code, payload.quantity)
    seq = next_sequence(db, GoodsReceiptRecord, "receipt_no", "GR")
    receipt = GoodsReceiptRecord(receipt_no=f"GR-{seq+1:06d}", order_id=order.id, order_no=order.order_no, supplier_name=order.supplier_name, factory_code=order.factory_code, material_code=line.material_code, material_name=line.material_name, received_quantity=payload.quantity, received_date=payload.expected_date, remark=f"供应商发货预通知：{payload.carrier} / {payload.tracking_no}，非实际收货", created_by="supplier:"+account.id)
    db.add(receipt)
    db.flush()
    row = SupplierDelivery(supplier_id=account.supplier_id, order_id=order.id, receipt_id=receipt.id, carrier=payload.carrier, tracking_no=payload.tracking_no, shipped_date=payload.shipped_date, expected_date=payload.expected_date)
    db.add(row)
    db.flush()
    audit(db, account, "dispatch", "supplier_delivery", row.id, f"订单 {order.order_no} 发货 {line.material_code} × {payload.quantity}")
    result = delivery_dict(db, row)
    db.commit()
    return result


@router.get("/supplier/deliveries")
def deliveries(account=Depends(supplier_user), db=Depends(get_db), page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    query = select(SupplierDelivery).where(SupplierDelivery.supplier_id == account.supplier_id).order_by(SupplierDelivery.created_at.desc(), SupplierDelivery.id)
    return page_result(db, query, page, page_size, lambda r: delivery_dict(db, r))


@router.get("/supplier-deliveries", dependencies=[Depends(editor)])
def internal_deliveries(db=Depends(get_db), page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    return page_result(db, select(SupplierDelivery).order_by(SupplierDelivery.created_at.desc(), SupplierDelivery.id), page, page_size, lambda r: delivery_dict(db, r))


@router.delete("/supplier/deliveries/{item_id}", status_code=204)
def cancel_delivery(item_id: str, account=Depends(supplier_user), db=Depends(get_db)):
    row = db.get(SupplierDelivery, item_id)
    if not row or row.supplier_id != account.supplier_id:
        raise HTTPException(404, "未找到交付记录")
    receipt = db.get(GoodsReceiptRecord, row.receipt_id)
    if not receipt or receipt.status != "draft":
        raise HTTPException(409, "采购方已收货，不能撤回")
    db.delete(receipt)
    db.delete(row)
    audit(db, account, "withdraw", "supplier_delivery", item_id, "供应商撤回未收货的发货预通知")
    db.commit()


def reconciliation_query(db, account):
    return select(ReconciliationRecord).join(PurchaseOrderRecord, PurchaseOrderRecord.id == ReconciliationRecord.order_id).where(ownership(db, account), ReconciliationRecord.status == "confirmed")


def reconciliation_dict(db, row):
    used = db.scalar(select(func.coalesce(func.sum(SupplierInvoiceRecord.amount), 0)).where(SupplierInvoiceRecord.reconciliation_id == row.id, SupplierInvoiceRecord.status != "rejected")) or Decimal(0)
    return {"id": row.id, "order_no": row.order_no, "reconciliation_no": row.reconciliation_no, "amount": str(row.amount+row.adjustment_amount), "remaining": str(max(Decimal(0), row.amount+row.adjustment_amount-used))}


@router.get("/supplier/reconciliations")
def reconciliations(account=Depends(supplier_user), db=Depends(get_db), page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    return page_result(db, reconciliation_query(db, account).order_by(ReconciliationRecord.created_at.desc()), page, page_size, lambda r: reconciliation_dict(db, r))


def invoice_dict(db, item):
    record = db.scalar(select(SupplierInvoiceFile).where(SupplierInvoiceFile.invoice_id == item.id))
    recon = db.get(ReconciliationRecord, item.reconciliation_id)
    return {"id": item.id, "invoice_no": item.invoice_no, "amount": str(item.amount), "tax_amount": str(item.tax_amount), "invoice_date": item.invoice_date, "status": item.status, "order_no": recon.order_no, "file_name": record.name if record else None}


@router.get("/supplier/invoices")
def invoices(account=Depends(supplier_user), db=Depends(get_db), page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    query = select(SupplierInvoiceRecord).join(ReconciliationRecord, ReconciliationRecord.id == SupplierInvoiceRecord.reconciliation_id).join(PurchaseOrderRecord, PurchaseOrderRecord.id == ReconciliationRecord.order_id).where(ownership(db, account)).order_by(SupplierInvoiceRecord.created_at.desc(), SupplierInvoiceRecord.id)
    return page_result(db, query, page, page_size, lambda r: invoice_dict(db, r))


@router.post("/supplier/invoices", status_code=201)
async def upload_invoice(reconciliation_id: str = Form(...), invoice_no: str = Form(..., min_length=2, max_length=64), amount: Decimal = Form(..., gt=0, max_digits=18, decimal_places=2), tax_amount: Decimal = Form(Decimal(0), ge=0, max_digits=18, decimal_places=2), invoice_date: date = Form(...), file: UploadFile = File(...), account=Depends(supplier_user), db=Depends(get_db)):
    if len(invoice_no.strip()) < 2:
        raise HTTPException(422, "请填写有效发票号码")
    recon = db.scalar(reconciliation_query(db, account).where(ReconciliationRecord.id == reconciliation_id))
    if not recon:
        raise HTTPException(404, "未找到您所属的已确认对账单")
    if tax_amount > amount:
        raise HTTPException(422, "税额不能大于发票含税金额")
    db.execute(update(ReconciliationRecord).where(ReconciliationRecord.id == recon.id).values(status=ReconciliationRecord.status))
    if amount > Decimal(reconciliation_dict(db, recon)["remaining"]):
        raise HTTPException(409, "累计发票金额不能超过对账金额")
    content = await file.read(10*1024*1024+1)
    name = Path(file.filename or "invoice").name
    ext = Path(name).suffix.lower()
    valid = (ext == ".pdf" and content.startswith(b"%PDF-")) or (ext == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n")) or (ext in {".jpg", ".jpeg"} and content.startswith(b"\xff\xd8\xff"))
    if not content or len(content) > 10*1024*1024 or len(name)>200 or not valid:
        raise HTTPException(422, "请上传10MB以内的PDF、PNG或JPEG发票，文件内容必须与扩展名一致")
    item = SupplierInvoiceRecord(invoice_no=invoice_no.strip(), reconciliation_id=recon.id, supplier_name=recon.supplier_name, amount=amount, tax_amount=tax_amount, invoice_date=invoice_date, created_by="supplier:"+account.id)
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "发票号码已存在，请勿重复上传") from exc
    record = SupplierInvoiceFile(supplier_id=account.supplier_id, invoice_id=item.id, name=name, storage_name=uuid4().hex+ext)
    db.add(record)
    FILES.mkdir(parents=True, exist_ok=True)
    path = FILES / record.storage_name
    try:
        path.write_bytes(content)
        audit(db, account, "upload", "supplier_invoice", item.id, f"供应商上传发票 {item.invoice_no}，待采购方审核")
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return invoice_dict(db, item)


def invoice_download(db, item_id, account=None):
    invoice = db.get(SupplierInvoiceRecord, item_id)
    record = db.scalar(select(SupplierInvoiceFile).where(SupplierInvoiceFile.invoice_id == item_id))
    if not invoice or not record or (account and record.supplier_id != account.supplier_id):
        raise HTTPException(404, "未找到发票附件")
    path = FILES / record.storage_name
    if not path.is_file():
        raise HTTPException(404, "发票文件不存在")
    return FileResponse(path, filename=record.name, headers={"X-Content-Type-Options":"nosniff", "Cache-Control":"no-store"})


@router.get("/supplier/invoices/{item_id}/file")
def supplier_file(item_id: str, account=Depends(supplier_user), db=Depends(get_db)):
    return invoice_download(db, item_id, account)


@router.delete("/supplier/invoices/{item_id}", status_code=204)
def withdraw_invoice(item_id: str, account=Depends(supplier_user), db=Depends(get_db)):
    record = db.scalar(select(SupplierInvoiceFile).where(SupplierInvoiceFile.invoice_id == item_id, SupplierInvoiceFile.supplier_id == account.supplier_id))
    item = db.get(SupplierInvoiceRecord, item_id)
    if not record or not item:
        raise HTTPException(404, "未找到您上传的发票")
    if item.status not in {"received", "rejected"} or db.scalar(select(PaymentRecord.id).where(PaymentRecord.invoice_id == item_id).limit(1)):
        raise HTTPException(409, "已验真或已进入付款流程的发票不能撤回")
    path = FILES / record.storage_name
    db.delete(item)
    db.delete(record)
    audit(db, account, "withdraw", "supplier_invoice", item_id, f"供应商撤回发票 {item.invoice_no}")
    db.commit()
    path.unlink(missing_ok=True)


@router.get("/invoices/{item_id}/file", dependencies=[Depends(editor)])
def internal_file(item_id: str, db=Depends(get_db)):
    return invoice_download(db, item_id)
