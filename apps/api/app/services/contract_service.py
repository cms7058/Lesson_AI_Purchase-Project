import json
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.contracts import Contract, ContractCreate, ContractStatus, ContractUpdate
from app.domain.persistence import (
    ContractElementRecord,
    ContractRecord,
    DocumentTemplateLinkRecord,
    PurchaseOrderRecord,
)
from app.services.numbering import next_sequence
from app.services.references import protect_references


def _template_id(db: Session, contract_id: str) -> str | None:
    return db.scalar(
        select(DocumentTemplateLinkRecord.template_id)
        .where(DocumentTemplateLinkRecord.document_type == "contract")
        .where(DocumentTemplateLinkRecord.document_id == contract_id)
        .order_by(DocumentTemplateLinkRecord.created_at.desc())
        .limit(1)
    )


def _contract_data(db: Session, contract_id: str) -> dict:
    record = db.get(ContractElementRecord, contract_id)
    if record is None:
        return {"elements": {}, "items": []}
    try:
        value = json.loads(record.data_json)
    except json.JSONDecodeError:
        value = {}
    return {"elements": value.get("elements", {}), "items": value.get("items", [])}


def _to_domain(db: Session, record: ContractRecord, template_id: str | None = None) -> Contract:
    return Contract(id=record.id, contract_no=record.contract_no, title=record.title, supplier_id=record.supplier_id, supplier_name=record.supplier_name, amount=record.amount, currency=record.currency, effective_date=record.effective_date, expiry_date=record.expiry_date, template_id=template_id, status=ContractStatus(record.status), created_at=record.created_at, **_contract_data(db, record.id))


def _save_contract_data(db: Session, contract_id: str, elements: dict | None, items: list[dict] | None) -> None:
    current = _contract_data(db, contract_id)
    data = {
        "elements": current["elements"] if elements is None else elements,
        "items": current["items"] if items is None else items,
    }
    record = db.get(ContractElementRecord, contract_id)
    if record is None:
        record = ContractElementRecord(contract_id=contract_id)
        db.add(record)
    record.data_json = json.dumps(data, ensure_ascii=False)


def _items_total(items: list[dict]) -> Decimal | None:
    if not items:
        return None
    total = Decimal(0)
    try:
        for item in items:
            quantity = Decimal(str(item.get("quantity") or 0))
            unit_price = Decimal(str(item.get("unit_price") or 0))
            tax_rate = Decimal(str(item.get("tax_rate") or 0))
            # tax_rate accepts either 0.13 or 13 in the teaching UI.
            if tax_rate > 1:
                tax_rate /= Decimal(100)
            total += quantity * unit_price * (Decimal(1) + tax_rate)
    except (InvalidOperation, TypeError):
        raise ValueError("合同明细中的数量、单价或税率格式不正确")
    return total.quantize(Decimal("0.01"))


class ContractService:
    def list_contracts(self, db: Session, page: int, page_size: int, keyword: str = "", status: str = "") -> tuple[Iterable[Contract], int]:
        query = select(ContractRecord)
        if keyword:
            pattern = f"%{keyword}%"
            query = query.where(or_(ContractRecord.contract_no.ilike(pattern), ContractRecord.title.ilike(pattern), ContractRecord.supplier_name.ilike(pattern)))
        if status:
            query = query.where(ContractRecord.status == status)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        records = db.scalars(query.order_by(ContractRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        return [_to_domain(db, record, _template_id(db, record.id)) for record in records], total

    def create_contract(self, db: Session, payload: ContractCreate, created_by: str) -> Contract:
        sequence = next_sequence(db, ContractRecord, "contract_no", "CT")
        calculated_amount = _items_total(payload.items)
        record = ContractRecord(contract_no=f"CT-{sequence + 1:06d}", title=payload.title, supplier_id=payload.supplier_id, supplier_name=payload.supplier_name, amount=calculated_amount if calculated_amount is not None else payload.amount, currency=payload.currency.upper(), effective_date=payload.effective_date, expiry_date=payload.expiry_date, created_by=created_by)
        db.add(record)
        db.flush()
        db.refresh(record)
        _save_contract_data(db, record.id, payload.elements, payload.items)
        db.flush()
        return _to_domain(db, record, str(payload.template_id) if payload.template_id else None)

    def update_contract(self, db: Session, contract_id: str, payload: ContractUpdate) -> Contract | None:
        record = db.get(ContractRecord, contract_id)
        if record is None:
            return None
        for field, value in payload.model_dump(exclude_none=True, exclude={"template_id", "elements", "items"}).items():
            setattr(record, field, value.value if isinstance(value, ContractStatus) else value)
        if "elements" in payload.model_fields_set or "items" in payload.model_fields_set:
            _save_contract_data(db, record.id, payload.elements, payload.items)
        if payload.items is not None:
            calculated_amount = _items_total(payload.items)
            if calculated_amount is not None:
                record.amount = calculated_amount
        db.flush(); db.refresh(record)
        return _to_domain(db, record, _template_id(db, record.id))

    def delete_contract(self, db: Session, contract_id: str) -> bool:
        record = db.get(ContractRecord, contract_id)
        if record is None:
            return False
        protect_references(db, [(PurchaseOrderRecord, PurchaseOrderRecord.contract_id == contract_id)], "合同")
        for link in db.scalars(select(DocumentTemplateLinkRecord).where(DocumentTemplateLinkRecord.document_type == "contract", DocumentTemplateLinkRecord.document_id == contract_id)):
            db.delete(link)
        elements = db.get(ContractElementRecord, contract_id)
        if elements:
            db.delete(elements)
        db.delete(record)
        return True

    def transition(self, db: Session, contract_id: str, source: str, target: str) -> Contract | None:
        record = db.get(ContractRecord, contract_id)
        if record is None or record.status != source:
            return None
        record.status = target
        db.flush()
        db.refresh(record)
        return _to_domain(db, record, _template_id(db, record.id))


contract_service = ContractService()
