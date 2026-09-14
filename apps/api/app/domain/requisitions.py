from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


class RequisitionStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONVERTED = "converted"
    CANCELLED = "cancelled"


class RequisitionPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class RequisitionLine(BaseModel):
    material_code: str = Field(min_length=1, max_length=64)
    material_name: str = Field(min_length=1, max_length=200)
    specification: str = Field(default="", max_length=500)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(default="件", min_length=1, max_length=24)
    estimated_unit_price: Decimal = Field(default=Decimal(0), ge=0)

    @computed_field
    @property
    def estimated_amount(self) -> Decimal:
        return (self.quantity * self.estimated_unit_price).quantize(Decimal("0.01"))


class RequisitionCreate(BaseModel):
    spare_plan_codes: list[str] = Field(default_factory=list,max_length=100)
    title: str = Field(min_length=2, max_length=200)
    factory_code: str = Field(min_length=1, max_length=64)
    department: str = Field(default="", max_length=100)
    cost_center: str = Field(default="", max_length=100)
    priority: RequisitionPriority = RequisitionPriority.NORMAL
    needed_date: date | None = None
    reason: str = Field(default="", max_length=1000)
    lines: list[RequisitionLine] = Field(min_length=1)


class RequisitionUpdate(BaseModel):
    spare_plan_codes: list[str] | None = Field(default=None,max_length=100)
    title: str | None = Field(default=None, min_length=2, max_length=200)
    factory_code: str | None = Field(default=None, min_length=1, max_length=64)
    department: str | None = Field(default=None, max_length=100)
    cost_center: str | None = Field(default=None, max_length=100)
    priority: RequisitionPriority | None = None
    needed_date: date | None = None
    reason: str | None = Field(default=None, max_length=1000)
    lines: list[RequisitionLine] | None = Field(default=None, min_length=1)


class ApprovalDecision(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=1000)


class RequisitionConversion(BaseModel):
    supplier_id: str = Field(min_length=1, max_length=64)
    supplier_name: str = Field(min_length=1, max_length=200)
    template_id: str | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    payment_terms: str = Field(default="", max_length=500)
    delivery_address: str = Field(default="", max_length=500)


class Requisition(RequisitionCreate):
    spare_analysis_snapshot: dict | None = None
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    request_no: str
    status: RequisitionStatus
    approval_comment: str
    approved_by: str
    approved_at: datetime | None
    order_id: UUID | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def estimated_total(self) -> Decimal:
        return sum((line.estimated_amount for line in self.lines), start=Decimal("0.00"))
