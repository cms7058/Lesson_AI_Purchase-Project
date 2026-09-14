from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


class OrderStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    SUPPLIER_CONFIRMED = "supplier_confirmed"
    PARTIALLY_DELIVERED = "partially_delivered"
    QUALITY_TRACKING = "quality_tracking"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderLineInput(BaseModel):
    material_code: str = Field(min_length=1, max_length=64)
    material_name: str = Field(min_length=1, max_length=200)
    specification: str = Field(default="", max_length=500)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=24)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.13"), ge=0, le=1)
    delivery_date: date | None = None

    @computed_field
    @property
    def net_amount(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    @computed_field
    @property
    def tax_amount(self) -> Decimal:
        return (self.net_amount * self.tax_rate).quantize(Decimal("0.01"))


class PurchaseOrderCreate(BaseModel):
    supplier_id: str = Field(min_length=1, max_length=64)
    supplier_name: str = Field(min_length=1, max_length=200)
    factory_code: str = Field(min_length=1, max_length=64)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    contract_id: str | None = None
    quotation_id: str | None = None
    template_id: str | None = None
    payment_terms: str = Field(default="", max_length=500)
    delivery_address: str = Field(default="", max_length=500)
    lines: list[OrderLineInput] = Field(min_length=1)


class PurchaseOrderUpdate(BaseModel):
    supplier_id: str | None = Field(default=None, min_length=1, max_length=64)
    lines: list[OrderLineInput] | None = Field(default=None, min_length=1)
    supplier_name: str | None = Field(default=None, min_length=1, max_length=200)
    factory_code: str | None = Field(default=None, min_length=1, max_length=64)
    payment_terms: str | None = Field(default=None, max_length=500)
    delivery_address: str | None = Field(default=None, max_length=500)
    template_id: str | None = None
    status: OrderStatus | None = None


class PurchaseOrder(PurchaseOrderCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    order_no: str
    status: OrderStatus = OrderStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def net_amount(self) -> Decimal:
        return sum((line.net_amount for line in self.lines), start=Decimal("0.00"))

    @computed_field
    @property
    def tax_amount(self) -> Decimal:
        return sum((line.tax_amount for line in self.lines), start=Decimal("0.00"))

    @computed_field
    @property
    def total_amount(self) -> Decimal:
        return self.net_amount + self.tax_amount
