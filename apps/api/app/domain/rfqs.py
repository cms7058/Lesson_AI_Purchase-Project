from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class RFQStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    AWARDED = "awarded"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class RFQLine(BaseModel):
    material_code: str = Field(min_length=1, max_length=64)
    material_name: str = Field(min_length=1, max_length=200)
    specification: str = Field(default="", max_length=500)
    quantity: float = Field(gt=0)
    unit: str = Field(default="件", min_length=1, max_length=24)


class RFQInvitation(BaseModel):
    supplier_id: str = Field(min_length=1, max_length=64)
    supplier_name: str = Field(min_length=1, max_length=200)
    status: str = "invited"
    quotation_id: UUID | None = None


class RFQCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    requisition_id: UUID | None = None
    deadline: date | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    lines: list[RFQLine] = Field(min_length=1)
    invitations: list[RFQInvitation] = Field(min_length=1)


class RFQUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    deadline: date | None = None
    lines: list[RFQLine] | None = Field(default=None, min_length=1)
    invitations: list[RFQInvitation] | None = Field(default=None, min_length=1)


class RFQResponseLink(BaseModel):
    quotation_id: UUID


class RFQAward(BaseModel):
    quotation_id: UUID
    method: str = Field(default="lowest", pattern="^(lowest|tco)$")


class RFQ(RFQCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    rfq_no: str
    status: RFQStatus
    awarded_quotation_id: UUID | None
    created_by: str
    created_at: datetime
    updated_at: datetime
