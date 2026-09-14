from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class TemplateType(StrEnum):
    ORDER = "order"
    QUOTATION = "quotation"
    CONTRACT = "contract"


class BusinessTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    template_type: TemplateType
    version: str = Field(default="1.0", min_length=1, max_length=24)
    content: str = Field(min_length=5, max_length=20000)


class BusinessTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    version: str | None = Field(default=None, min_length=1, max_length=24)
    content: str | None = Field(default=None, min_length=5, max_length=20000)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class BusinessTemplate(BusinessTemplateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    status: str
    created_by: str
    created_at: datetime
    engine: str = "text_v1"
    original_filename: str | None = None
    file_size: int | None = None
    validation_status: str | None = None
    placeholders: list[str] = Field(default_factory=list)


class WordTemplateValidation(BaseModel):
    template_id: UUID
    valid: bool
    status: str
    placeholders: list[str]
    unknown_placeholders: list[str]
    warnings: list[str]


class RenderedDocument(BaseModel):
    template_id: UUID
    template_name: str
    template_type: TemplateType
    source_type: str
    source_id: UUID
    content: str
    placeholders_replaced: list[str]
    placeholders_unresolved: list[str]
