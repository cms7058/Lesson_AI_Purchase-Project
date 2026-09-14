import json
import re
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.persistence import (
    BusinessTemplateRecord,
    DocumentTemplateLinkRecord,
    GeneratedBusinessDocumentRecord,
    ManagedWordTemplateRecord,
    PurchaseOrderRecord,
    WordTemplateFileRecord,
)
from app.domain.templates import (
    BusinessTemplate,
    BusinessTemplateCreate,
    BusinessTemplateUpdate,
    RenderedDocument,
    TemplateType,
)
from app.services.references import protect_references

PLACEHOLDER_PATTERN = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")


def _to_domain(record: BusinessTemplateRecord, word_file: WordTemplateFileRecord | None = None) -> BusinessTemplate:
    return BusinessTemplate(
        id=record.id,
        name=record.name,
        template_type=TemplateType(record.template_type),
        version=record.version,
        content=record.content,
        status=record.status,
        created_by=record.created_by,
        created_at=record.created_at,
        engine="docx_v1" if word_file else "text_v1",
        original_filename=word_file.original_filename if word_file else None,
        file_size=word_file.file_size if word_file else None,
        validation_status=word_file.validation_status if word_file else None,
        placeholders=json.loads(word_file.placeholders_json) if word_file else [],
    )


class TemplateService:
    def get_template(self, db: Session, template_id: str) -> BusinessTemplate | None:
        record = db.get(BusinessTemplateRecord, template_id)
        if record is None:
            return None
        word_file = db.scalar(select(WordTemplateFileRecord).where(WordTemplateFileRecord.template_id == template_id))
        return _to_domain(record, word_file)

    def list_templates(
        self, db: Session, page: int = 1, page_size: int = 20
    ) -> tuple[Iterable[BusinessTemplate], int]:
        statement = select(BusinessTemplateRecord).order_by(BusinessTemplateRecord.created_at.desc())
        total = db.scalar(select(func.count()).select_from(BusinessTemplateRecord)) or 0
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        records = list(db.scalars(statement))
        word_files = {
            item.template_id: item
            for item in db.scalars(
                select(WordTemplateFileRecord).where(
                    WordTemplateFileRecord.template_id.in_([record.id for record in records])
                )
            )
        } if records else {}
        return [_to_domain(record, word_files.get(record.id)) for record in records], total

    def create_template(
        self, db: Session, payload: BusinessTemplateCreate, created_by: str
    ) -> BusinessTemplate:
        record = BusinessTemplateRecord(
            name=payload.name,
            template_type=payload.template_type,
            version=payload.version,
            content=payload.content,
            status="active",
            created_by=created_by,
        )
        db.add(record)
        db.flush()
        db.refresh(record)
        return _to_domain(record)

    def update_template(
        self, db: Session, template_id: str, payload: BusinessTemplateUpdate
    ) -> BusinessTemplate | None:
        record = db.get(BusinessTemplateRecord, template_id)
        if record is None:
            return None
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(record, field, value)
        db.flush()
        db.refresh(record)
        return _to_domain(record, db.scalar(select(WordTemplateFileRecord).where(WordTemplateFileRecord.template_id == record.id)))

    def delete_template(self, db: Session, template_id: str) -> bool:
        record = db.get(BusinessTemplateRecord, template_id)
        if record is None:
            return False
        protect_references(db, [(PurchaseOrderRecord, PurchaseOrderRecord.template_id == template_id), (DocumentTemplateLinkRecord, DocumentTemplateLinkRecord.template_id == template_id), (GeneratedBusinessDocumentRecord, GeneratedBusinessDocumentRecord.template_id == template_id)], "模板")
        word_file = db.scalar(select(WordTemplateFileRecord).where(WordTemplateFileRecord.template_id == template_id))
        if word_file:
            from pathlib import Path
            path = Path(word_file.storage_path)
            if path.exists():
                path.unlink()
            db.delete(word_file)
        managed = db.get(ManagedWordTemplateRecord, template_id)
        if managed:
            db.delete(managed)
        db.delete(record)
        return True

    def render_order(self, db: Session, template_id: str, order_id: str) -> RenderedDocument | None:
        template = db.get(BusinessTemplateRecord, template_id)
        if template is None:
            return None
        order = db.scalar(
            select(PurchaseOrderRecord)
            .where(PurchaseOrderRecord.id == order_id)
            .options(selectinload(PurchaseOrderRecord.lines))
        )
        if order is None:
            return None
        first_line = order.lines[0] if order.lines else None
        values = {
            "order_no": order.order_no,
            "supplier_name": order.supplier_name,
            "supplier_id": order.supplier_id,
            "factory_code": order.factory_code,
            "currency": order.currency,
            "payment_terms": order.payment_terms,
            "delivery_address": order.delivery_address,
            "material_code": first_line.material_code if first_line else "",
            "material_name": first_line.material_name if first_line else "",
            "quantity": str(first_line.quantity) if first_line else "",
            "unit": first_line.unit if first_line else "",
            "unit_price": str(first_line.unit_price) if first_line else "",
        }
        keys = PLACEHOLDER_PATTERN.findall(template.content)
        content = template.content
        for key, value in values.items():
            content = content.replace(f"{{{{{key}}}}}", value)
        unresolved = sorted({key for key in keys if key not in values})
        replaced = sorted({key for key in keys if key in values})
        return RenderedDocument(
            template_id=template.id,
            template_name=template.name,
            template_type=TemplateType(template.template_type),
            source_type="purchase_order",
            source_id=order.id,
            content=content,
            placeholders_replaced=replaced,
            placeholders_unresolved=unresolved,
        )


template_service = TemplateService()
