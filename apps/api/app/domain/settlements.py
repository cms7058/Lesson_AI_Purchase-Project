from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ReconciliationCreate(BaseModel):
    order_id: UUID
    amount: Decimal = Field(ge=0)
    adjustment_amount: Decimal = Field(default=Decimal(0))
    remark: str = Field(default="", max_length=1000)


class ReconciliationUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, ge=0)
    adjustment_amount: Decimal | None = None
    remark: str | None = Field(default=None, max_length=1000)


class Reconciliation(ReconciliationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    reconciliation_no: str
    order_no: str
    supplier_name: str
    status: str
    created_by: str
    created_at: datetime


class InvoiceCreate(BaseModel):
    invoice_no: str = Field(min_length=2, max_length=64)
    reconciliation_id: UUID
    amount: Decimal = Field(gt=0)
    tax_amount: Decimal = Field(default=Decimal(0), ge=0)
    invoice_date: date | None = None


class InvoiceUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)
    invoice_date: date | None = None


class SupplierInvoice(InvoiceCreate):
    attachment_name: str | None = None
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    supplier_name: str
    status: str
    created_by: str
    created_at: datetime


class PaymentCreate(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=0)
    planned_date: date | None = None


class PaymentUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)
    planned_date: date | None = None


class Payment(PaymentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    payment_no: str
    invoice_no: str
    supplier_name: str
    paid_date: date | None
    status: str
    created_by: str
    created_at: datetime
