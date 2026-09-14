from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.fulfillment import StatusAction
from app.domain.persistence import (
    PaymentRecord,
    PurchaseOrderRecord,
    ReconciliationRecord,
    SupplierInvoiceRecord,
)
from app.domain.settlements import (
    InvoiceCreate,
    InvoiceUpdate,
    Payment,
    PaymentCreate,
    PaymentUpdate,
    Reconciliation,
    ReconciliationCreate,
    ReconciliationUpdate,
    SupplierInvoice,
)
from app.domain.supplier_execution import SupplierInvoiceFile
from app.services.audit_service import write_audit_log
from app.services.numbering import next_sequence

router = APIRouter(tags=["settlements"])
EDITORS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}


def _require(user: CurrentUser) -> None:
    if user.role not in EDITORS: raise HTTPException(status_code=403, detail="当前角色无权处理采购结算")


def _page(db: Session, model, page: int, page_size: int):
    total=db.scalar(select(func.count()).select_from(model)) or 0
    items=list(db.scalars(select(model).order_by(model.created_at.desc()).offset((page-1)*page_size).limit(page_size)))
    return items,total


def _audit(db: Session,user: CurrentUser,action: str,kind: str,item_id: str,detail: str)->None:
    write_audit_log(db,actor_id=user.user_id,actor_role=user.role,action=action,resource_type=kind,resource_id=item_id,detail=detail)


@router.get("/reconciliations",response_model=Page[Reconciliation])
def list_reconciliations(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    items,total=_page(db,ReconciliationRecord,page,page_size);return Page(items=items,page=page,page_size=page_size,total=total)


@router.post("/reconciliations",response_model=Reconciliation,status_code=201)
def create_reconciliation(payload:ReconciliationCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);order=db.get(PurchaseOrderRecord,str(payload.order_id))
    if order is None: raise HTTPException(status_code=404,detail="未找到采购订单")
    seq = next_sequence(db, ReconciliationRecord, "reconciliation_no", "RC")
    item=ReconciliationRecord(reconciliation_no=f"RC-{seq+1:06d}",order_id=order.id,order_no=order.order_no,supplier_name=order.supplier_name,amount=payload.amount,adjustment_amount=payload.adjustment_amount,remark=payload.remark,created_by=user.user_id)
    db.add(item);db.flush();_audit(db,user,"create","reconciliation",item.id,f"创建对账单 {item.reconciliation_no}");db.commit();db.refresh(item);return item


@router.patch("/reconciliations/{item_id}",response_model=Reconciliation)
def update_reconciliation(item_id:str,payload:ReconciliationUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);item=db.get(ReconciliationRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到对账单")
    if item.status!="draft": raise HTTPException(status_code=409,detail="只有草稿对账单可以修改")
    for key,value in payload.model_dump(exclude_none=True).items():setattr(item,key,value)
    _audit(db,user,"update","reconciliation",item_id,f"更新对账单 {item.reconciliation_no}");db.commit();db.refresh(item);return item


@router.post("/reconciliations/{item_id}/confirm",response_model=Reconciliation)
def confirm_reconciliation(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);item=db.get(ReconciliationRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到对账单")
    if item.status!="draft": raise HTTPException(status_code=409,detail="对账单状态不允许确认")
    item.status="confirmed";_audit(db,user,"confirm","reconciliation",item_id,f"确认对账单 {item.reconciliation_no}");db.commit();db.refresh(item);return item


@router.delete("/reconciliations/{item_id}",status_code=204)
def delete_reconciliation(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);item=db.get(ReconciliationRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到对账单")
    if item.status!="draft": raise HTTPException(status_code=409,detail="只有草稿对账单可以删除")
    db.delete(item);_audit(db,user,"delete","reconciliation",item_id,"删除对账单");db.commit()


@router.get("/invoices",response_model=Page[SupplierInvoice])
def list_invoices(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    items,total=_page(db,SupplierInvoiceRecord,page,page_size)
    files = {f.invoice_id: f.name for f in db.scalars(select(SupplierInvoiceFile).where(SupplierInvoiceFile.invoice_id.in_([i.id for i in items])))}
    return Page(items=[SupplierInvoice.model_validate(i).model_copy(update={"attachment_name":files.get(i.id)}) for i in items],page=page,page_size=page_size,total=total)


@router.post("/invoices",response_model=SupplierInvoice,status_code=201)
def create_invoice(payload:InvoiceCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);reconciliation=db.get(ReconciliationRecord,str(payload.reconciliation_id))
    if reconciliation is None: raise HTTPException(status_code=404,detail="未找到对账单")
    if reconciliation.status!="confirmed": raise HTTPException(status_code=409,detail="对账单尚未确认")
    item=SupplierInvoiceRecord(invoice_no=payload.invoice_no,reconciliation_id=reconciliation.id,supplier_name=reconciliation.supplier_name,amount=payload.amount,tax_amount=payload.tax_amount,invoice_date=payload.invoice_date or datetime.now(UTC).date(),created_by=user.user_id)
    db.add(item)
    try: db.flush()
    except IntegrityError as error: db.rollback();raise HTTPException(status_code=409,detail="发票号码已存在") from error
    _audit(db,user,"create","supplier_invoice",item.id,f"登记发票 {item.invoice_no}");db.commit();db.refresh(item);return item


@router.patch("/invoices/{item_id}",response_model=SupplierInvoice)
def update_invoice(item_id:str,payload:InvoiceUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);item=db.get(SupplierInvoiceRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到发票")
    if item.status!="received": raise HTTPException(status_code=409,detail="只有待验真发票可以修改")
    if db.scalar(select(SupplierInvoiceFile.id).where(SupplierInvoiceFile.invoice_id == item_id)):
        raise HTTPException(409, "供应商上传发票不能直接修改，请驳回后由供应商撤回重传")
    for key,value in payload.model_dump(exclude_none=True).items():setattr(item,key,value)
    _audit(db,user,"update","supplier_invoice",item_id,f"更新发票 {item.invoice_no}");db.commit();db.refresh(item);return item


@router.patch("/invoices/{item_id}/status",response_model=SupplierInvoice)
def invoice_status(item_id:str,payload:StatusAction,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);item=db.get(SupplierInvoiceRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到发票")
    if item.status!="received" or payload.status not in {"verified","rejected"}: raise HTTPException(status_code=409,detail="发票状态流转不合法")
    item.status=payload.status;_audit(db,user,"status","supplier_invoice",item_id,f"发票变更为 {payload.status}");db.commit();db.refresh(item);return item


@router.delete("/invoices/{item_id}",status_code=204)
def delete_invoice(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);item=db.get(SupplierInvoiceRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到发票")
    if item.status!="received": raise HTTPException(status_code=409,detail="只有待验真发票可以删除")
    if db.scalar(select(SupplierInvoiceFile.id).where(SupplierInvoiceFile.invoice_id == item_id)):
        raise HTTPException(409, "供应商上传发票请先驳回，由供应商撤回重传")
    db.delete(item);_audit(db,user,"delete","supplier_invoice",item_id,"删除发票");db.commit()


@router.get("/payments",response_model=Page[Payment])
def list_payments(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    items,total=_page(db,PaymentRecord,page,page_size);return Page(items=items,page=page,page_size=page_size,total=total)


@router.post("/payments",response_model=Payment,status_code=201)
def create_payment(payload:PaymentCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);invoice=db.get(SupplierInvoiceRecord,str(payload.invoice_id))
    if invoice is None: raise HTTPException(status_code=404,detail="未找到发票")
    if invoice.status!="verified": raise HTTPException(status_code=409,detail="发票尚未验真")
    reserved=db.scalar(select(func.coalesce(func.sum(PaymentRecord.amount),0)).where(PaymentRecord.invoice_id==invoice.id)) or 0
    if reserved+payload.amount>invoice.amount: raise HTTPException(status_code=409,detail="累计付款及计划金额不能超过发票金额")
    seq = next_sequence(db, PaymentRecord, "payment_no", "PAY")
    item=PaymentRecord(payment_no=f"PAY-{seq+1:06d}",invoice_id=invoice.id,invoice_no=invoice.invoice_no,supplier_name=invoice.supplier_name,amount=payload.amount,planned_date=payload.planned_date,created_by=user.user_id)
    db.add(item);db.flush();_audit(db,user,"create","payment",item.id,f"创建付款计划 {item.payment_no}");db.commit();db.refresh(item);return item


@router.patch("/payments/{item_id}",response_model=Payment)
def update_payment(item_id:str,payload:PaymentUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);item=db.get(PaymentRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到付款计划")
    if item.status!="planned": raise HTTPException(status_code=409,detail="只有待审批付款计划可以修改")
    if payload.amount is not None:
        invoice=db.get(SupplierInvoiceRecord,item.invoice_id)
        reserved=db.scalar(select(func.coalesce(func.sum(PaymentRecord.amount),0)).where(PaymentRecord.invoice_id==item.invoice_id,PaymentRecord.id!=item_id)) or 0
        if invoice is None or reserved+payload.amount>invoice.amount:raise HTTPException(status_code=409,detail="累计付款及计划金额不能超过发票金额")
    for key,value in payload.model_dump(exclude_none=True).items():setattr(item,key,value)
    _audit(db,user,"update","payment",item_id,f"更新付款计划 {item.payment_no}");db.commit();db.refresh(item);return item


@router.patch("/payments/{item_id}/status",response_model=Payment)
def payment_status(item_id:str,payload:StatusAction,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);item=db.get(PaymentRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到付款计划")
    allowed={"planned":"approved","approved":"paid"}
    if allowed.get(item.status)!=payload.status: raise HTTPException(status_code=409,detail="付款状态流转不合法")
    item.status=payload.status
    if payload.status=="paid":item.paid_date=datetime.now(UTC).date()
    _audit(db,user,"status","payment",item_id,f"付款计划变更为 {payload.status}");db.commit();db.refresh(item);return item


@router.delete("/payments/{item_id}",status_code=204)
def delete_payment(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _require(user);item=db.get(PaymentRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到付款计划")
    if item.status!="planned": raise HTTPException(status_code=409,detail="只有待审批付款计划可以删除")
    db.delete(item);_audit(db,user,"delete","payment",item_id,"删除付款计划");db.commit()
