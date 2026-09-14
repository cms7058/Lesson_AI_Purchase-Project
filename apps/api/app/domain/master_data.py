from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class SupplierStatus(StrEnum):
    CANDIDATE = "candidate"
    QUALIFIED = "qualified"
    SUSPENDED = "suspended"
    BLACKLISTED = "blacklisted"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SupplierBase(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=200)
    unified_credit_code: str = Field(default="", max_length=32)
    category: str = Field(default="", max_length=100)
    status: SupplierStatus = SupplierStatus.CANDIDATE
    risk_level: RiskLevel = RiskLevel.LOW
    contact: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=500)


class SupplierCreate(SupplierBase):
    model_config = ConfigDict(extra="forbid")


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=200)
    unified_credit_code: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=100)
    status: SupplierStatus | None = None
    risk_level: RiskLevel | None = None
    contact: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=500)


class Supplier(SupplierBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    created_by: str
    created_at: datetime
    updated_at: datetime


from app.domain.material_policy import SpareClassification

class MaterialBase(BaseModel):
    spare_classification: SpareClassification = Field(default_factory=SpareClassification)
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    specification: str = Field(default="", max_length=500)
    category: str = Field(default="", max_length=100)
    unit: str = Field(default="件", min_length=1, max_length=24)
    standard_price: Decimal = Field(default=Decimal(0), ge=0)
    safety_stock: Decimal = Field(default=Decimal(0), ge=0)
    lead_time_days: int = Field(default=0, ge=0, le=9999)
    active: bool = True


class MaterialCreate(MaterialBase):
    pass


class MaterialUpdate(BaseModel):
    spare_classification: SpareClassification | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    specification: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=24)
    standard_price: Decimal | None = Field(default=None, ge=0)
    safety_stock: Decimal | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0, le=9999)
    active: bool | None = None


class Material(MaterialBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    created_by: str
    created_at: datetime
    updated_at: datetime


class FactoryBase(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=200)
    address: str = Field(default="", max_length=500)
    contact: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=40)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    daily_receiving_capacity: Decimal = Field(default=Decimal(0), ge=0)
    active: bool = True


class FactoryCreate(FactoryBase):
    pass


class FactoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    contact: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    daily_receiving_capacity: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None


class Factory(FactoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    created_by: str
    created_at: datetime
    updated_at: datetime
