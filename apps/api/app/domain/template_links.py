from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    ORDER = "order"
    QUOTATION = "quotation"
    CONTRACT = "contract"


class TemplateLinkCreate(BaseModel):
    document_type: DocumentType
    document_id: UUID
    template_id: UUID


class TemplateLink(TemplateLinkCreate):
    id: UUID = Field(default_factory=uuid4)
    created_by: str
    created_at: datetime
