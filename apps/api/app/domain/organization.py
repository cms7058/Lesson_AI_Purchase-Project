from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: UUID | None = None
    code_segment: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{1,8}$")


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None


class MaterialCategory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    level: int
    parent_id: UUID | None
    path_name: str
    active: bool
    created_at: datetime
    updated_at: datetime


class MaterialAssignment(BaseModel):
    material_id: UUID
    category_id: UUID


class StaffCreate(BaseModel):
    user_code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(default="", max_length=200)
    department: str = Field(default="采购部", max_length=120)
    title: str = Field(default="", max_length=120)
    role: str = Field(default="buyer", pattern="^(admin|procurement_manager|buyer|analyst|auditor|instructor|student)$")
    status: str = Field(default="active", pattern="^(active|disabled)$")


class StaffUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, pattern="^(admin|procurement_manager|buyer|analyst|auditor|instructor|student)$")
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class StaffUser(StaffCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_by: str
    created_at: datetime
    updated_at: datetime


class BuyerAuthorizationCreate(BaseModel):
    buyer_id: UUID
    category_id: UUID
    valid_from: date
    valid_to: date

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_to < self.valid_from:
            raise ValueError("授权结束日期不能早于开始日期")
        return self


class BuyerAuthorizationUpdate(BaseModel):
    valid_from: date | None = None
    valid_to: date | None = None
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class BuyerAuthorization(BaseModel):
    id: UUID
    buyer_id: UUID
    buyer_name: str
    category_id: UUID
    category_code: str
    category_name: str
    category_level: int
    valid_from: date
    valid_to: date
    status: str
    effective: bool
    created_at: datetime


class SupplierCategoryLinkCreate(BaseModel):
    supplier_id: UUID
    category_id: UUID
    qualification_status: str = Field(default="qualified", pattern="^(candidate|qualified|suspended)$")


class SupplierCategoryLinkUpdate(BaseModel):
    qualification_status: str = Field(pattern="^(candidate|qualified|suspended)$")


class SupplierCategoryLink(BaseModel):
    id: UUID
    supplier_id: UUID
    supplier_code: str
    supplier_name: str
    category_id: UUID
    category_code: str
    category_name: str
    category_level: int
    qualification_status: str
    created_at: datetime
