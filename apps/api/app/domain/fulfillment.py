from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReceiptCreate(BaseModel):
    order_id: UUID
    material_code: str = Field(min_length=1, max_length=64)
    material_name: str = Field(min_length=1, max_length=200)
    received_quantity: Decimal = Field(gt=0)
    received_date: date | None = None
    remark: str = Field(default="", max_length=1000)


class ReceiptUpdate(BaseModel):
    received_quantity: Decimal | None = Field(default=None, gt=0)
    received_date: date | None = None
    remark: str | None = Field(default=None, max_length=1000)


class Receipt(ReceiptCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    receipt_no: str
    order_no: str
    supplier_name: str
    factory_code: str
    accepted_quantity: Decimal
    rejected_quantity: Decimal
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class InspectionCreate(BaseModel):
    receipt_id: UUID
    inspected_quantity: Decimal = Field(gt=0)
    accepted_quantity: Decimal = Field(ge=0)
    rejected_quantity: Decimal = Field(ge=0)
    rework_quantity: Decimal = Field(default=Decimal(0), ge=0)
    defect_description: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def quantities_match(self):
        if self.accepted_quantity + self.rejected_quantity != self.inspected_quantity:
            raise ValueError("合格数量与不合格数量之和必须等于检验数量")
        if self.rework_quantity > self.inspected_quantity:
            raise ValueError("返工数量不能超过检验数量")
        return self


class Inspection(InspectionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    inspection_no: str
    receipt_no: str
    result: str
    inspected_by: str
    inspected_at: datetime


class ReturnCreate(BaseModel):
    receipt_id: UUID
    quantity: Decimal = Field(gt=0)
    reason: str = Field(min_length=2, max_length=1000)


class PurchaseReturn(ReturnCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    return_no: str
    receipt_no: str
    supplier_name: str
    material_code: str
    status: str
    created_by: str
    created_at: datetime


class StatusAction(BaseModel):
    status: str
