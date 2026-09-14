from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class ContractCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    supplier_id: str = Field(min_length=1, max_length=64)
    supplier_name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    effective_date: date | None = None
    expiry_date: date | None = None
    template_id: UUID | None = None
    elements: dict = Field(default_factory=dict)
    items: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_date and self.expiry_date and self.expiry_date < self.effective_date:
            raise ValueError("合同失效日期不能早于生效日期")
        return self


class ContractUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    supplier_id: str | None = Field(default=None, min_length=1, max_length=64)
    supplier_name: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    effective_date: date | None = None
    expiry_date: date | None = None
    template_id: UUID | None = None
    elements: dict | None = None
    items: list[dict] | None = None


class ContractDecision(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=1000)


class Contract(ContractCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    contract_no: str
    status: ContractStatus
    created_at: datetime
