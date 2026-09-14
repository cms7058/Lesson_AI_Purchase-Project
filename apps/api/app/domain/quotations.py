from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


class QuotationLineInput(BaseModel):
    material_code: str = Field(min_length=1, max_length=64)
    material_name: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=24)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.13"), ge=0, le=1)
    logistics_cost: Decimal = Field(default=Decimal(0), ge=0)
    expected_quality_loss: Decimal = Field(default=Decimal(0), ge=0)

    @computed_field
    @property
    def tco_amount(self) -> Decimal:
        goods_amount = self.quantity * self.unit_price * (Decimal(1) + self.tax_rate)
        return (goods_amount + self.logistics_cost + self.expected_quality_loss).quantize(Decimal("0.01"))


class QuotationCreate(BaseModel):
    supplier_id: str = Field(min_length=1, max_length=64)
    supplier_name: str = Field(min_length=1, max_length=200)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    validity_days: int = Field(default=30, ge=1, le=365)
    delivery_days: int = Field(default=14, ge=0, le=999)
    service_score: Decimal = Field(default=Decimal(80), ge=0, le=100)
    quality_pass_rate: Decimal = Field(default=Decimal(98), ge=0, le=100)
    source_type: str = Field(default="manual", pattern="^(manual|ocr|api)$")
    lines: list[QuotationLineInput] = Field(min_length=1)


class QuotationUpdate(BaseModel):
    template_id: UUID | None = None
    supplier_id: str | None = Field(default=None, min_length=1, max_length=64)
    supplier_name: str | None = Field(default=None, min_length=1, max_length=200)
    source_type: str | None = Field(default=None, pattern="^(manual|ocr|api)$")
    lines: list[QuotationLineInput] | None = Field(default=None, min_length=1)
    delivery_days: int | None = Field(default=None, ge=0, le=999)
    service_score: Decimal | None = Field(default=None, ge=0, le=100)
    quality_pass_rate: Decimal | None = Field(default=None, ge=0, le=100)
    validity_days: int | None = Field(default=None, ge=1, le=365)


class Quotation(QuotationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    quotation_no: str
    created_at: datetime
    template_id: str | None = None


class BidComparisonItem(BaseModel):
    quotation_id: UUID
    quotation_no: str
    supplier_name: str
    unit_price: Decimal
    tco_amount: Decimal
    delivery_days: int
    service_score: Decimal
    quality_pass_rate: Decimal
    evaluation_score: Decimal


class BidComparison(BaseModel):
    material_code: str
    quantity: Decimal
    currency: str
    recommended_quotation_id: UUID | None
    methodology: str
    items: list[BidComparisonItem]
