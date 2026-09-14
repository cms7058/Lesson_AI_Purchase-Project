from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.fulfillment import (
    Inspection,
    InspectionCreate,
    PurchaseReturn,
    Receipt,
    ReceiptCreate,
    ReceiptUpdate,
    ReturnCreate,
    StatusAction,
)
from app.domain.persistence import (
    GoodsReceiptRecord,
    PurchaseOrderRecord,
    PurchaseReturnRecord,
    QualityInspectionRecord,
)
from app.domain.supplier_execution import SupplierDelivery
from app.services.audit_service import write_audit_log
from app.services.numbering import next_sequence
from app.services.order_service import sync_fulfillment_status

router = APIRouter(tags=["fulfillment"])
EDITORS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}


def _require(user: CurrentUser) -> None:
    if user.role not in EDITORS:
        raise HTTPException(status_code=403, detail="当前角色无权处理订单履约")


def _page(db: Session, model, page: int, page_size: int):
    total = db.scalar(select(func.count()).select_from(model)) or 0
    ordering = model.created_at if hasattr(model, "created_at") else model.inspected_at
    items = list(db.scalars(select(model).order_by(ordering.desc()).offset((page - 1) * page_size).limit(page_size)))
    return items, total


def _audit(db: Session, user: CurrentUser, action: str, resource_type: str, resource_id: str, detail: str) -> None:
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action=action, resource_type=resource_type, resource_id=resource_id, detail=detail)


def _receipt_capacity(db, order, material_code, quantity, exclude_id=""):
    ordered=sum(line.quantity for line in order.lines if line.material_code==material_code)
    used=db.scalar(select(func.coalesce(func.sum(GoodsReceiptRecord.received_quantity),0)).where(GoodsReceiptRecord.order_id==order.id,GoodsReceiptRecord.material_code==material_code,GoodsReceiptRecord.id!=exclude_id)) or 0
    returned = db.scalar(select(func.coalesce(func.sum(PurchaseReturnRecord.quantity), 0)).join(GoodsReceiptRecord, GoodsReceiptRecord.id == PurchaseReturnRecord.receipt_id).where(GoodsReceiptRecord.order_id == order.id, GoodsReceiptRecord.material_code == material_code, GoodsReceiptRecord.id != exclude_id, PurchaseReturnRecord.status == "completed")) or 0
    used -= returned
    if used+quantity>ordered:
        raise HTTPException(status_code=409,detail="累计收货数量（含待确认单）不能超过订单数量")


@router.get("/receipts", response_model=Page[Receipt])
def list_receipts(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> Page[Receipt]:
    items, total = _page(db, GoodsReceiptRecord, page, page_size)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post("/receipts", response_model=Receipt, status_code=201)
def create_receipt(payload: ReceiptCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _require(user)
    order = db.get(PurchaseOrderRecord, str(payload.order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="未找到采购订单")
    if order.status == "cancelled":
        raise HTTPException(status_code=409, detail="已取消订单不能新增收货")
    if not any(line.material_code == payload.material_code for line in order.lines):
        raise HTTPException(status_code=409, detail="收货物料不在采购订单中")
    _receipt_capacity(db,order,payload.material_code,payload.received_quantity)
    sequence = next_sequence(db, GoodsReceiptRecord, "receipt_no", "GR")
    item = GoodsReceiptRecord(receipt_no=f"GR-{sequence + 1:06d}", order_id=order.id, order_no=order.order_no, supplier_name=order.supplier_name, factory_code=order.factory_code, material_code=payload.material_code, material_name=payload.material_name, received_quantity=payload.received_quantity, received_date=payload.received_date or datetime.now(UTC).date(), remark=payload.remark, created_by=user.user_id)
    db.add(item); db.flush(); _audit(db, user, "create", "goods_receipt", item.id, f"创建收货单 {item.receipt_no}"); db.commit(); db.refresh(item); return item


@router.patch("/receipts/{item_id}", response_model=Receipt)
def update_receipt(item_id: str, payload: ReceiptUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _require(user); item = db.get(GoodsReceiptRecord, item_id)
    if item is None: raise HTTPException(status_code=404, detail="未找到收货单")
    if item.status != "draft": raise HTTPException(status_code=409, detail="只有草稿收货单可以修改")
    if payload.received_quantity is not None:
        order=db.get(PurchaseOrderRecord,item.order_id)
        if order is None:raise HTTPException(status_code=409,detail="关联订单不存在")
        _receipt_capacity(db,order,item.material_code,payload.received_quantity,item.id)
    for key, value in payload.model_dump(exclude_none=True).items(): setattr(item, key, value)
    db.flush(); _audit(db, user, "update", "goods_receipt", item_id, f"更新收货单 {item.receipt_no}"); db.commit(); db.refresh(item); return item


@router.post("/receipts/{item_id}/confirm", response_model=Receipt)
def confirm_receipt(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _require(user); item = db.get(GoodsReceiptRecord, item_id)
    if item is None: raise HTTPException(status_code=404, detail="未找到收货单")
    if item.status != "draft": raise HTTPException(status_code=409, detail="收货单状态不允许确认")
    if db.scalar(select(SupplierDelivery.id).where(SupplierDelivery.receipt_id == item_id)):
        item.received_date = datetime.now(UTC).date()
    item.status = "received"; _audit(db, user, "confirm", "goods_receipt", item_id, f"确认收货 {item.receipt_no}"); sync_fulfillment_status(db, item.order_id); db.commit(); db.refresh(item); return item


@router.delete("/receipts/{item_id}", status_code=204)
def delete_receipt(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _require(user); item = db.get(GoodsReceiptRecord, item_id)
    if item is None: raise HTTPException(status_code=404, detail="未找到收货单")
    if item.status != "draft": raise HTTPException(status_code=409, detail="只有草稿收货单可以删除")
    if db.scalar(select(SupplierDelivery.id).where(SupplierDelivery.receipt_id == item_id)):
        raise HTTPException(409, "该收货单关联供应商发货，请供应商先撤回发货预通知")
    db.delete(item); _audit(db, user, "delete", "goods_receipt", item_id, "删除收货单"); db.commit()


@router.get("/inspections", response_model=Page[Inspection])
def list_inspections(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> Page[Inspection]:
    items, total = _page(db, QualityInspectionRecord, page, page_size)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post("/inspections", response_model=Inspection, status_code=201)
def create_inspection(payload: InspectionCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _require(user); receipt = db.get(GoodsReceiptRecord, str(payload.receipt_id))
    if receipt is None: raise HTTPException(status_code=404, detail="未找到收货单")
    if receipt.status != "received": raise HTTPException(status_code=409, detail="收货单尚未确认或已经质检")
    if payload.inspected_quantity > receipt.received_quantity-receipt.accepted_quantity-receipt.rejected_quantity: raise HTTPException(status_code=409, detail="检验数量不能超过剩余未检数量")
    sequence = next_sequence(db, QualityInspectionRecord, "inspection_no", "QI")
    result = "passed" if payload.rejected_quantity == 0 else ("failed" if payload.accepted_quantity == 0 else "partial")
    item = QualityInspectionRecord(inspection_no=f"QI-{sequence + 1:06d}", receipt_id=receipt.id, receipt_no=receipt.receipt_no, inspected_quantity=payload.inspected_quantity, accepted_quantity=payload.accepted_quantity, rejected_quantity=payload.rejected_quantity, rework_quantity=payload.rework_quantity, result=result, defect_description=payload.defect_description, inspected_by=user.user_id)
    receipt.accepted_quantity += payload.accepted_quantity
    receipt.rejected_quantity += payload.rejected_quantity
    receipt.status = "inspected" if receipt.accepted_quantity+receipt.rejected_quantity == receipt.received_quantity else "received"
    db.add(item); db.flush(); _audit(db, user, "inspect", "quality_inspection", item.id, f"记录质检 {item.inspection_no}"); sync_fulfillment_status(db, receipt.order_id); db.commit(); db.refresh(item); return item


@router.get("/returns", response_model=Page[PurchaseReturn])
def list_returns(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> Page[PurchaseReturn]:
    items, total = _page(db, PurchaseReturnRecord, page, page_size)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post("/returns", response_model=PurchaseReturn, status_code=201)
def create_return(payload: ReturnCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _require(user); receipt = db.get(GoodsReceiptRecord, str(payload.receipt_id))
    if receipt is None: raise HTTPException(status_code=404, detail="未找到收货单")
    if receipt.status != "inspected" or receipt.rejected_quantity <= 0: raise HTTPException(status_code=409, detail="该收货单没有可退货的不合格品")
    returned=db.scalar(select(func.coalesce(func.sum(PurchaseReturnRecord.quantity),0)).where(PurchaseReturnRecord.receipt_id==receipt.id)) or 0
    if returned+payload.quantity > receipt.rejected_quantity: raise HTTPException(status_code=409, detail="累计退货数量不能超过不合格数量")
    sequence = next_sequence(db, PurchaseReturnRecord, "return_no", "RT")
    item = PurchaseReturnRecord(return_no=f"RT-{sequence + 1:06d}", receipt_id=receipt.id, receipt_no=receipt.receipt_no, supplier_name=receipt.supplier_name, material_code=receipt.material_code, quantity=payload.quantity, reason=payload.reason, created_by=user.user_id)
    db.add(item); db.flush(); _audit(db, user, "create", "purchase_return", item.id, f"创建退货单 {item.return_no}"); db.commit(); db.refresh(item); return item


@router.patch("/returns/{item_id}/status", response_model=PurchaseReturn)
def update_return_status(item_id: str, payload: StatusAction, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _require(user); item = db.get(PurchaseReturnRecord, item_id)
    if item is None: raise HTTPException(status_code=404, detail="未找到退货单")
    allowed={"draft":"sent","sent":"completed"}
    if allowed.get(item.status) != payload.status: raise HTTPException(status_code=409, detail="退货状态流转不合法")
    item.status=payload.status; _audit(db,user,"status","purchase_return",item_id,f"退货单变更为 {payload.status}"); receipt = db.get(GoodsReceiptRecord, item.receipt_id); sync_fulfillment_status(db, receipt.order_id); db.commit(); db.refresh(item); return item


@router.delete("/returns/{item_id}", status_code=204)
def delete_return(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _require(user); item=db.get(PurchaseReturnRecord,item_id)
    if item is None: raise HTTPException(status_code=404,detail="未找到退货单")
    if item.status!="draft": raise HTTPException(status_code=409,detail="只有草稿退货单可以删除")
    db.delete(item); _audit(db,user,"delete","purchase_return",item_id,"删除退货单"); db.commit()
