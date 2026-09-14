from collections.abc import Iterable

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.orders import (
    OrderLineInput,
    OrderStatus,
    PurchaseOrder,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)
from app.domain.persistence import (
    BusinessTemplateRecord,
    DocumentTemplateLinkRecord,
    GoodsReceiptRecord,
    PurchaseOrderLineRecord,
    PurchaseOrderRecord,
    PurchaseRequisitionRecord,
    PurchaseReturnRecord,
    ReconciliationRecord,
)
from app.services.numbering import next_sequence
from app.services.references import protect_references


def fulfillment_status(db, order):
    receipts = list(db.scalars(select(GoodsReceiptRecord).where(GoodsReceiptRecord.order_id == order.id, GoodsReceiptRecord.status != "draft")))
    if not receipts:
        return None
    returned = dict(db.execute(select(PurchaseReturnRecord.receipt_id, func.sum(PurchaseReturnRecord.quantity)).where(PurchaseReturnRecord.receipt_id.in_([r.id for r in receipts]), PurchaseReturnRecord.status == "completed").group_by(PurchaseReturnRecord.receipt_id)).all())
    if any(r.status == "received" or r.rejected_quantity > returned.get(r.id, 0) or r.accepted_quantity + r.rejected_quantity < r.received_quantity for r in receipts):
        return "quality_tracking"
    required = {}
    for line in order.lines:
        required[line.material_code] = required.get(line.material_code, 0) + line.quantity
    complete = all(sum(r.accepted_quantity for r in receipts if r.material_code == code) >= quantity for code, quantity in required.items())
    return "completed" if complete else "partially_delivered"


def sync_fulfillment_status(db, order_id):
    db.flush()
    order = db.get(PurchaseOrderRecord, order_id)
    if order and order.status != "cancelled":
        derived = fulfillment_status(db, order)
        if derived:
            order.status = derived


def _to_domain(record: PurchaseOrderRecord) -> PurchaseOrder:
    return PurchaseOrder(
        id=record.id,
        order_no=record.order_no,
        supplier_id=record.supplier_id,
        supplier_name=record.supplier_name,
        factory_code=record.factory_code,
        currency=record.currency,
        contract_id=record.contract_id,
        quotation_id=record.quotation_id,
        template_id=record.template_id,
        payment_terms=record.payment_terms,
        delivery_address=record.delivery_address,
        status=OrderStatus(record.status),
        created_at=record.created_at,
        lines=[
            OrderLineInput(
                material_code=line.material_code,
                material_name=line.material_name,
                specification=line.specification,
                quantity=line.quantity,
                unit=line.unit,
                unit_price=line.unit_price,
                tax_rate=line.tax_rate,
                delivery_date=line.delivery_date,
            )
            for line in record.lines
        ],
    )


class OrderService:
    """Persistent purchase-order repository."""

    def list_orders(self, db: Session, page: int = 1, page_size: int = 20) -> tuple[Iterable[PurchaseOrder], int]:
        statement = (
            select(PurchaseOrderRecord)
            .options(selectinload(PurchaseOrderRecord.lines))
            .order_by(PurchaseOrderRecord.created_at.desc())
        )
        total = db.scalar(select(func.count()).select_from(PurchaseOrderRecord)) or 0
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        return [_to_domain(item) for item in db.scalars(statement)], total

    def create_order(self, db: Session, payload: PurchaseOrderCreate, created_by: str) -> PurchaseOrder:
        self._validate_template(db, payload.template_id)
        sequence = next_sequence(db, PurchaseOrderRecord, "order_no", "PO")
        order = PurchaseOrderRecord(
            order_no=f"PO-{sequence + 1:06d}",
            supplier_id=payload.supplier_id,
            supplier_name=payload.supplier_name,
            factory_code=payload.factory_code,
            currency=payload.currency.upper(),
            contract_id=payload.contract_id,
            quotation_id=payload.quotation_id,
            template_id=payload.template_id,
            payment_terms=payload.payment_terms,
            delivery_address=payload.delivery_address,
            created_by=created_by,
        )
        for line in payload.lines:
            order.lines.append(
                PurchaseOrderLineRecord(
                    material_code=line.material_code,
                    material_name=line.material_name,
                    specification=line.specification,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    tax_rate=line.tax_rate,
                    delivery_date=line.delivery_date,
                )
            )
        db.add(order)
        db.flush()
        db.refresh(order, attribute_names=["lines"])
        return _to_domain(order)

    def update_order(
        self, db: Session, order_id: str, payload: PurchaseOrderUpdate
    ) -> PurchaseOrder | None:
        record = db.get(PurchaseOrderRecord, order_id)
        if record is None:
            return None
        if payload.status and payload.status != record.status:
            derived = fulfillment_status(db, record)
            if derived and payload.status != derived:
                raise HTTPException(409, "已开始收货，采购状态由收货质检记录自动计算，不允许手工覆盖")
            if not derived and payload.status in {"completed", "quality_tracking", "partially_delivered"}:
                raise HTTPException(409, "该采购状态需要实际收货质检记录")
            if record.status == "cancelled":
                raise HTTPException(409, "已取消订单不能恢复状态")
        if record.status != "draft" and any(key != "status" for key in payload.model_fields_set):
            raise HTTPException(status_code=409, detail="只有草稿订单可以修改业务内容")
        if "template_id" in payload.model_fields_set:
            self._validate_template(db, payload.template_id)
        for field, value in payload.model_dump(exclude_none=True, exclude={"lines"}).items():
            setattr(record, field, value.value if isinstance(value, OrderStatus) else value)
        if payload.lines is not None:
            from app.domain.project_costs import ProjectAllocation
            protect_references(db, [(ProjectAllocation, ProjectAllocation.order_id == order_id)], '项目分摊订单明细')
            protect_references(db, [(GoodsReceiptRecord, GoodsReceiptRecord.order_id == order_id)], "订单明细")
            record.lines = [PurchaseOrderLineRecord(**line.model_dump(exclude={"net_amount", "tax_amount"})) for line in payload.lines]
        if "template_id" in payload.model_fields_set:
            record.template_id = payload.template_id or None
        db.flush()
        db.refresh(record, attribute_names=["lines"])
        return _to_domain(record)

    def delete_order(self, db: Session, order_id: str) -> bool:
        from app.domain.project_costs import ProjectAllocation
        protect_references(db, [(ProjectAllocation, ProjectAllocation.order_id == order_id)], '项目分摊订单')
        from app.domain.order_buyer import OrderBuyerAssignment
        record = db.get(PurchaseOrderRecord, order_id)
        if record is None:
            return False
        if record.status not in {"draft", "cancelled"}:
            raise HTTPException(status_code=409, detail="仅草稿或已取消且无关联记录的订单可以删除")
        protect_references(db, [(GoodsReceiptRecord, GoodsReceiptRecord.order_id == order_id), (ReconciliationRecord, ReconciliationRecord.order_id == order_id), (PurchaseRequisitionRecord, PurchaseRequisitionRecord.order_id == order_id)], "订单")
        assignment = db.get(OrderBuyerAssignment, order_id)
        if assignment:
            db.delete(assignment)
            db.flush()
        db.delete(record)
        for link in db.scalars(select(DocumentTemplateLinkRecord).where(DocumentTemplateLinkRecord.document_type == "order", DocumentTemplateLinkRecord.document_id == order_id)):
            db.delete(link)
        return True

    @staticmethod
    def _validate_template(db: Session, template_id: str | None) -> None:
        if not template_id:
            return
        template = db.get(BusinessTemplateRecord, str(template_id))
        if template is None:
            raise HTTPException(status_code=404, detail="未找到订单模板")
        if template.template_type != "order" or template.status != "active":
            raise HTTPException(status_code=409, detail="请选择已启用的订单模板")


order_service = OrderService()
