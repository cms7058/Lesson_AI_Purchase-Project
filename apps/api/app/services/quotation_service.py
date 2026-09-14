from collections.abc import Iterable
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.persistence import (
    BusinessTemplateRecord,
    DocumentTemplateLinkRecord,
    PurchaseOrderRecord,
    QuotationLineRecord,
    QuotationRecord,
    RFQInvitationRecord,
    RFQRecord,
)
from app.domain.quotations import (
    BidComparison,
    BidComparisonItem,
    Quotation,
    QuotationCreate,
    QuotationLineInput,
    QuotationUpdate,
)
from app.services.numbering import next_sequence
from app.services.references import protect_references


def _to_domain(record: QuotationRecord, db: Session) -> Quotation:
    return Quotation(
        id=record.id,
        template_id=db.scalar(select(DocumentTemplateLinkRecord.template_id).where(DocumentTemplateLinkRecord.document_type=="quotation",DocumentTemplateLinkRecord.document_id==record.id).order_by(DocumentTemplateLinkRecord.created_at.desc()).limit(1)),
        quotation_no=record.quotation_no,
        supplier_id=record.supplier_id,
        supplier_name=record.supplier_name,
        currency=record.currency,
        validity_days=record.validity_days,
        delivery_days=record.delivery_days,
        service_score=record.service_score,
        quality_pass_rate=record.quality_pass_rate,
        source_type=record.source_type,
        created_at=record.created_at,
        lines=[
            QuotationLineInput(
                material_code=line.material_code,
                material_name=line.material_name,
                quantity=line.quantity,
                unit=line.unit,
                unit_price=line.unit_price,
                tax_rate=line.tax_rate,
                logistics_cost=line.logistics_cost,
                expected_quality_loss=line.expected_quality_loss,
            )
            for line in record.lines
        ],
    )


class QuotationService:
    def list_quotations(
        self, db: Session, page: int = 1, page_size: int = 20
    ) -> tuple[Iterable[Quotation], int]:
        statement = (
            select(QuotationRecord)
            .options(selectinload(QuotationRecord.lines))
            .order_by(QuotationRecord.created_at.desc())
        )
        total = db.scalar(select(func.count()).select_from(QuotationRecord)) or 0
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        return [_to_domain(record, db) for record in db.scalars(statement)], total

    def create_quotation(
        self, db: Session, payload: QuotationCreate, created_by: str
    ) -> Quotation:
        sequence = next_sequence(db, QuotationRecord, "quotation_no", "RFQ")
        quotation = QuotationRecord(
            quotation_no=f"RFQ-{sequence + 1:06d}",
            supplier_id=payload.supplier_id,
            supplier_name=payload.supplier_name,
            currency=payload.currency.upper(),
            validity_days=payload.validity_days,
            delivery_days=payload.delivery_days,
            service_score=payload.service_score,
            quality_pass_rate=payload.quality_pass_rate,
            source_type=payload.source_type,
            created_by=created_by,
        )
        for line in payload.lines:
            quotation.lines.append(
                QuotationLineRecord(
                    material_code=line.material_code,
                    material_name=line.material_name,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    tax_rate=line.tax_rate,
                    logistics_cost=line.logistics_cost,
                    expected_quality_loss=line.expected_quality_loss,
                )
            )
        db.add(quotation)
        db.flush()
        db.refresh(quotation, attribute_names=["lines"])
        return _to_domain(quotation, db)

    def update_quotation(
        self, db: Session, quotation_id: str, payload: QuotationUpdate, created_by: str = "system"
    ) -> Quotation | None:
        record = db.get(QuotationRecord, quotation_id)
        if record is None:
            return None
        if "template_id" in payload.model_fields_set:
            if payload.template_id:
                template = db.get(BusinessTemplateRecord, str(payload.template_id))
                if template is None or template.template_type != "quotation" or template.status != "active":
                    raise HTTPException(status_code=409, detail="请选择已启用的报价单模板")
            for link in db.scalars(select(DocumentTemplateLinkRecord).where(DocumentTemplateLinkRecord.document_type == "quotation", DocumentTemplateLinkRecord.document_id == quotation_id)):
                db.delete(link)
            if payload.template_id:
                db.add(DocumentTemplateLinkRecord(document_type="quotation", document_id=quotation_id, template_id=str(payload.template_id), created_by=created_by))
        for field, value in payload.model_dump(exclude_none=True, exclude={"lines", "template_id"}).items():
            setattr(record, field, value)
        if payload.lines is not None:
            record.lines = [QuotationLineRecord(**line.model_dump(exclude={"tco_amount"})) for line in payload.lines]
        db.flush()
        db.refresh(record, attribute_names=["lines"])
        return _to_domain(record, db)

    def delete_quotation(self, db: Session, quotation_id: str) -> bool:
        record = db.get(QuotationRecord, quotation_id)
        if record is None:
            return False
        protect_references(db, [(PurchaseOrderRecord, PurchaseOrderRecord.quotation_id == quotation_id), (RFQInvitationRecord, RFQInvitationRecord.quotation_id == quotation_id), (RFQRecord, RFQRecord.awarded_quotation_id == quotation_id)], "报价单")
        for link in db.scalars(select(DocumentTemplateLinkRecord).where(DocumentTemplateLinkRecord.document_type == "quotation", DocumentTemplateLinkRecord.document_id == quotation_id)):
            db.delete(link)
        db.delete(record)
        return True

    def compare(self, db: Session, material_code: str, quantity: Decimal, currency: str | None = None) -> BidComparison:
        statement = (
            select(QuotationRecord)
            .join(QuotationRecord.lines)
            .where(QuotationLineRecord.material_code == material_code)
            .options(selectinload(QuotationRecord.lines))
        )
        if currency:
            statement = statement.where(QuotationRecord.currency == currency)
        quotations = list(db.scalars(statement).unique())
        if len({item.currency for item in quotations}) > 1:
            raise ValueError("报价包含多种币种，请选择币种后分别比价")
        matching_lines = [line for item in quotations for line in item.lines if line.material_code == material_code]
        if len({line.unit for line in matching_lines}) > 1:
            raise ValueError("同物料报价单位不一致，请统一计量单位后比价")
        if any(sum(line.material_code == material_code for line in item.lines) > 1 for item in quotations):
            raise ValueError("报价单内存在多条同物料明细，请先明确唯一采购报价后比价")
        comparison_rows: list[tuple[QuotationRecord, QuotationLineRecord, Decimal]] = []
        for quotation in quotations:
            line = next(line for line in quotation.lines if line.material_code == material_code)
            tco = (
                quantity * line.unit_price * (Decimal(1) + line.tax_rate)
                + line.logistics_cost
                + line.expected_quality_loss
            ).quantize(Decimal("0.01"))
            comparison_rows.append((quotation, line, tco))

        minimum_tco = min((row[2] for row in comparison_rows), default=Decimal(0))
        items: list[BidComparisonItem] = []
        for quotation, line, tco in comparison_rows:
            price_score = Decimal(0) if tco == 0 else (minimum_tco / tco) * Decimal(55)
            delivery_score = max(Decimal(0), Decimal(20) - Decimal(quotation.delivery_days) / 3)
            service_score = quotation.service_score * Decimal("0.10")
            quality_score = quotation.quality_pass_rate * Decimal("0.15")
            items.append(
                BidComparisonItem(
                    quotation_id=quotation.id,
                    quotation_no=quotation.quotation_no,
                    supplier_name=quotation.supplier_name,
                    unit_price=line.unit_price,
                    tco_amount=tco,
                    delivery_days=quotation.delivery_days,
                    service_score=quotation.service_score,
                    quality_pass_rate=quotation.quality_pass_rate,
                    evaluation_score=(price_score + delivery_score + service_score + quality_score).quantize(
                        Decimal("0.01")
                    ),
                )
            )
        items.sort(key=lambda item: item.evaluation_score, reverse=True)
        return BidComparison(
            material_code=material_code,
            quantity=quantity,
            currency=quotations[0].currency if quotations else "CNY",
            recommended_quotation_id=items[0].quotation_id if items else None,
            methodology="TOC=含税货款+物流成本+预期质量损失；综合分=价格55%+交期20%+服务10%+质量15%。",
            items=items,
        )


quotation_service = QuotationService()
