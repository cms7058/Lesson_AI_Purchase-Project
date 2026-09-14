from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.domain.persistence import QuotationRecord, RFQInvitationRecord, RFQLineRecord, RFQRecord
from app.domain.rfqs import RFQ, RFQCreate, RFQInvitation, RFQLine, RFQStatus, RFQUpdate
from app.services.numbering import next_sequence


def _to_domain(record: RFQRecord) -> RFQ:
    return RFQ(id=record.id, rfq_no=record.rfq_no, title=record.title, requisition_id=record.requisition_id, deadline=record.deadline, currency=record.currency, status=record.status, awarded_quotation_id=record.awarded_quotation_id, created_by=record.created_by, created_at=record.created_at, updated_at=record.updated_at, lines=[RFQLine(material_code=line.material_code, material_name=line.material_name, specification=line.specification, quantity=float(line.quantity), unit=line.unit) for line in record.lines], invitations=[RFQInvitation(supplier_id=item.supplier_id, supplier_name=item.supplier_name, status=item.status, quotation_id=item.quotation_id) for item in record.invitations])


def _replace_children(record: RFQRecord, lines, invitations) -> None:
    if lines is not None:
        record.lines.clear()
        record.lines.extend(RFQLineRecord(material_code=item.material_code, material_name=item.material_name, specification=item.specification, quantity=item.quantity, unit=item.unit) for item in lines)
    if invitations is not None:
        record.invitations.clear()
        record.invitations.extend(RFQInvitationRecord(supplier_id=item.supplier_id, supplier_name=item.supplier_name) for item in invitations)


class RFQService:
    def get(self, db: Session, item_id: str) -> RFQRecord | None:
        return db.scalar(select(RFQRecord).where(RFQRecord.id == item_id).options(selectinload(RFQRecord.lines), selectinload(RFQRecord.invitations)))

    def list(self, db: Session, page: int, page_size: int, keyword: str = "", status: str = "") -> tuple[list[RFQ], int]:
        filters = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(RFQRecord.rfq_no.ilike(pattern), RFQRecord.title.ilike(pattern)))
        if status:
            filters.append(RFQRecord.status == status)
        total = db.scalar(select(func.count()).select_from(RFQRecord).where(*filters)) or 0
        statement = select(RFQRecord).where(*filters).options(selectinload(RFQRecord.lines), selectinload(RFQRecord.invitations)).order_by(RFQRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return [_to_domain(item) for item in db.scalars(statement)], total

    def create(self, db: Session, payload: RFQCreate, created_by: str) -> RFQ:
        sequence = next_sequence(db, RFQRecord, "rfq_no", "XJ")
        record = RFQRecord(rfq_no=f"XJ-{sequence + 1:06d}", title=payload.title, requisition_id=str(payload.requisition_id) if payload.requisition_id else None, deadline=payload.deadline, currency=payload.currency.upper(), created_by=created_by)
        _replace_children(record, payload.lines, payload.invitations)
        db.add(record); db.flush(); db.refresh(record, attribute_names=["lines", "invitations"])
        return _to_domain(record)

    def update(self, db: Session, item_id: str, payload: RFQUpdate) -> tuple[RFQ | None, str | None]:
        record = self.get(db, item_id)
        if record is None:
            return None, "not_found"
        if record.status != RFQStatus.DRAFT:
            return None, "locked"
        values = payload.model_dump(exclude_none=True, exclude={"lines", "invitations"})
        for key, value in values.items():
            setattr(record, key, value)
        _replace_children(record, payload.lines, payload.invitations)
        db.flush(); db.refresh(record, attribute_names=["lines", "invitations"])
        return _to_domain(record), None

    def publish(self, db: Session, item_id: str) -> tuple[RFQ | None, str | None]:
        record = self.get(db, item_id)
        if record is None:
            return None, "not_found"
        if record.status != RFQStatus.DRAFT:
            return None, "invalid_status"
        record.status = RFQStatus.PUBLISHED
        db.flush(); db.refresh(record, attribute_names=["lines", "invitations"])
        return _to_domain(record), None

    def link_response(self, db: Session, item_id: str, quotation_id: str) -> tuple[RFQ | None, str | None]:
        record = self.get(db, item_id)
        quote = db.get(QuotationRecord, quotation_id)
        if record is None or quote is None:
            return None, "not_found"
        if record.status != RFQStatus.PUBLISHED:
            return None, "invalid_status"
        invitation = next((item for item in record.invitations if item.supplier_id == quote.supplier_id), None)
        if invitation is None:
            return None, "not_invited"
        invitation.status = "responded"; invitation.quotation_id = quotation_id
        db.flush(); db.refresh(record, attribute_names=["lines", "invitations"])
        return _to_domain(record), None

    def award(self, db: Session, item_id: str, quotation_id: str) -> tuple[RFQ | None, str | None]:
        record = self.get(db, item_id)
        if record is None:
            return None, "not_found"
        if record.status != RFQStatus.PUBLISHED:
            return None, "invalid_status"
        if not any(item.quotation_id == quotation_id for item in record.invitations):
            return None, "response_missing"
        record.status = RFQStatus.AWARDED; record.awarded_quotation_id = quotation_id
        db.flush(); db.refresh(record, attribute_names=["lines", "invitations"])
        return _to_domain(record), None

    def delete(self, db: Session, item_id: str) -> tuple[bool, str | None]:
        record = db.get(RFQRecord, item_id)
        if record is None:
            return False, "not_found"
        if record.status != RFQStatus.DRAFT:
            return False, "locked"
        db.delete(record)
        return True, None


rfq_service = RFQService()
