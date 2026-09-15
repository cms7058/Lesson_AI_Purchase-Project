import json
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.domain.aviation_mro import AviationRequisitionProfile, AviationRequisitionProfileRecord
from app.domain.material_policy import SpareRequestSnapshot
from app.domain.orders import OrderLineInput, PurchaseOrderCreate
from app.domain.persistence import PurchaseRequisitionLineRecord, PurchaseRequisitionRecord
from app.domain.requisitions import (
    Requisition,
    RequisitionConversion,
    RequisitionCreate,
    RequisitionLine,
    RequisitionStatus,
    RequisitionUpdate,
)
from app.services.numbering import next_sequence
from app.services.order_service import order_service


def _to_domain(record: PurchaseRequisitionRecord) -> Requisition:
    snapshot = object_session(record).get(SpareRequestSnapshot, record.id)
    analysis = json.loads(snapshot.payload) if snapshot else None
    aviation = object_session(record).get(AviationRequisitionProfileRecord, record.id)
    return Requisition(
        aviation_profile=AviationRequisitionProfile.model_validate(aviation, from_attributes=True)
        if aviation
        else None,
        spare_plan_codes=[r["material_code"] for r in analysis["items"]] if analysis else [],
        spare_analysis_snapshot=analysis,
        id=record.id,
        request_no=record.request_no,
        title=record.title,
        factory_code=record.factory_code,
        department=record.department,
        cost_center=record.cost_center,
        priority=record.priority,
        needed_date=record.needed_date,
        reason=record.reason,
        status=record.status,
        approval_comment=record.approval_comment,
        approved_by=record.approved_by,
        approved_at=record.approved_at,
        order_id=record.order_id,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
        lines=[
            RequisitionLine(
                material_code=line.material_code,
                material_name=line.material_name,
                specification=line.specification,
                quantity=line.quantity,
                unit=line.unit,
                estimated_unit_price=line.estimated_unit_price,
            )
            for line in record.lines
        ],
    )


def _replace_lines(record: PurchaseRequisitionRecord, lines: list[RequisitionLine]) -> None:
    record.lines.clear()
    for line in lines:
        record.lines.append(
            PurchaseRequisitionLineRecord(
                material_code=line.material_code,
                material_name=line.material_name,
                specification=line.specification,
                quantity=line.quantity,
                unit=line.unit,
                estimated_unit_price=line.estimated_unit_price,
            )
        )


class RequisitionService:
    def save_aviation_profile(self, db, record, payload):
        previous = db.get(AviationRequisitionProfileRecord, record.id)
        if payload is None:
            if previous:
                db.delete(previous)
            return
        if not previous:
            previous = AviationRequisitionProfileRecord(requisition_id=record.id)
            db.add(previous)
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload
        for key, value in values.items():
            setattr(previous, key, value)
        db.flush()

    def save_spare_snapshot(self, db, record, codes):
        previous = db.get(SpareRequestSnapshot, record.id)
        if not codes:
            if previous:
                db.delete(previous)
            return
        from app.services.spare_ranking import rank_spares

        analysis = rank_spares(db, material_codes=codes)
        analysis["items"] = [r for r in analysis["items"] if r["material_code"] in codes]
        if set(codes) != {r["material_code"] for r in analysis["items"]} or set(codes) != {
            l.material_code for l in record.lines
        }:
            raise HTTPException(422, "备件计划物料必须仍为有效备件，并与申请明细完全一致")
        analysis["captured_at"] = datetime.now(UTC).isoformat()
        analysis["requested_quantities"] = {
            l.material_code: float(l.quantity) for l in record.lines
        }
        if not previous:
            previous = SpareRequestSnapshot(request_id=record.id)
            db.add(previous)
        previous.payload = json.dumps(analysis, ensure_ascii=False)
        db.flush()

    def list(
        self, db: Session, page: int, page_size: int, keyword: str = "", status: str = ""
    ) -> tuple[list[Requisition], int]:
        filters = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    PurchaseRequisitionRecord.request_no.ilike(pattern),
                    PurchaseRequisitionRecord.title.ilike(pattern),
                    PurchaseRequisitionRecord.department.ilike(pattern),
                )
            )
        if status:
            filters.append(PurchaseRequisitionRecord.status == status)
        total = (
            db.scalar(select(func.count()).select_from(PurchaseRequisitionRecord).where(*filters))
            or 0
        )
        statement = (
            select(PurchaseRequisitionRecord)
            .where(*filters)
            .options(selectinload(PurchaseRequisitionRecord.lines))
            .order_by(PurchaseRequisitionRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_domain(item) for item in db.scalars(statement)], total

    def get_record(self, db: Session, item_id: str) -> PurchaseRequisitionRecord | None:
        return db.scalar(
            select(PurchaseRequisitionRecord)
            .where(PurchaseRequisitionRecord.id == item_id)
            .options(selectinload(PurchaseRequisitionRecord.lines))
        )

    def create(self, db: Session, payload: RequisitionCreate, created_by: str) -> Requisition:
        sequence = next_sequence(db, PurchaseRequisitionRecord, "request_no", "PR")
        record = PurchaseRequisitionRecord(
            request_no=f"PR-{sequence + 1:06d}",
            title=payload.title,
            factory_code=payload.factory_code,
            department=payload.department,
            cost_center=payload.cost_center,
            priority=payload.priority,
            needed_date=payload.needed_date,
            reason=payload.reason,
            created_by=created_by,
        )
        _replace_lines(record, payload.lines)
        db.add(record)
        db.flush()
        db.refresh(record, attribute_names=["lines"])
        self.save_spare_snapshot(db, record, payload.spare_plan_codes)
        self.save_aviation_profile(db, record, payload.aviation_profile)
        return _to_domain(record)

    def update(
        self, db: Session, item_id: str, payload: RequisitionUpdate
    ) -> tuple[Requisition | None, str | None]:
        record = self.get_record(db, item_id)
        if record is None:
            return None, "not_found"
        if record.status not in {RequisitionStatus.DRAFT, RequisitionStatus.REJECTED}:
            return None, "locked"
        values = payload.model_dump(exclude_none=True)
        codes = values.pop("spare_plan_codes", None)
        aviation = values.pop("aviation_profile", None)
        lines = values.pop("lines", None)
        for key, value in values.items():
            setattr(record, key, value.value if hasattr(value, "value") else value)
        if lines is not None:
            _replace_lines(record, payload.lines or [])
            if codes is None:
                previous = db.get(SpareRequestSnapshot, record.id)
                if previous:
                    codes = [r["material_code"] for r in json.loads(previous.payload)["items"]]
        if codes is not None:
            self.save_spare_snapshot(db, record, codes)
        if "aviation_profile" in payload.model_fields_set:
            self.save_aviation_profile(db, record, aviation)
        record.status = RequisitionStatus.DRAFT
        record.approval_comment = ""
        db.flush()
        db.refresh(record, attribute_names=["lines"])
        return _to_domain(record), None

    def submit(self, db: Session, item_id: str) -> tuple[Requisition | None, str | None]:
        record = self.get_record(db, item_id)
        if record is None:
            return None, "not_found"
        if record.status not in {RequisitionStatus.DRAFT, RequisitionStatus.REJECTED}:
            return None, "invalid_status"
        aviation = db.get(AviationRequisitionProfileRecord, item_id)
        if aviation and aviation.demand_type in {"aog", "non_routine"}:
            if not aviation.work_package or not aviation.finding_no or not aviation.evidence:
                raise HTTPException(
                    422, "航空AOG/Non-routine需求提交前必须填写维修工作包、异常发现编号和证据依据"
                )
            if aviation.demand_type == "aog" and aviation.required_within_hours <= 0:
                raise HTTPException(422, "AOG需求必须填写要求到货小时数")
        record.status = RequisitionStatus.PENDING_APPROVAL
        db.flush()
        db.refresh(record, attribute_names=["lines"])
        return _to_domain(record), None

    def decide(
        self, db: Session, item_id: str, approved: bool, comment: str, approver: str
    ) -> tuple[Requisition | None, str | None]:
        record = self.get_record(db, item_id)
        if record is None:
            return None, "not_found"
        if record.status != RequisitionStatus.PENDING_APPROVAL:
            return None, "invalid_status"
        record.status = RequisitionStatus.APPROVED if approved else RequisitionStatus.REJECTED
        record.approval_comment = comment
        record.approved_by = approver
        record.approved_at = datetime.now(UTC)
        db.flush()
        db.refresh(record, attribute_names=["lines"])
        return _to_domain(record), None

    def convert(self, db: Session, item_id: str, payload: RequisitionConversion, created_by: str):
        record = self.get_record(db, item_id)
        if record is None:
            return None, "not_found"
        if record.status != RequisitionStatus.APPROVED:
            return None, "invalid_status"
        order_payload = PurchaseOrderCreate(
            supplier_id=payload.supplier_id,
            supplier_name=payload.supplier_name,
            factory_code=record.factory_code,
            currency=payload.currency,
            template_id=payload.template_id,
            payment_terms=payload.payment_terms,
            delivery_address=payload.delivery_address,
            lines=[
                OrderLineInput(
                    material_code=line.material_code,
                    material_name=line.material_name,
                    specification=line.specification,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.estimated_unit_price,
                    delivery_date=record.needed_date,
                )
                for line in record.lines
            ],
        )
        order = order_service.create_order(db, order_payload, created_by)
        record.status = RequisitionStatus.CONVERTED
        record.order_id = str(order.id)
        db.flush()
        return order, None

    def delete(self, db: Session, item_id: str) -> tuple[bool, str | None]:
        record = db.get(PurchaseRequisitionRecord, item_id)
        if record is None:
            return False, "not_found"
        if record.status not in {RequisitionStatus.DRAFT, RequisitionStatus.REJECTED}:
            return False, "locked"
        aviation = db.get(AviationRequisitionProfileRecord, item_id)
        if aviation:
            db.delete(aviation)
        db.delete(record)
        return True, None


requisition_service = RequisitionService()
