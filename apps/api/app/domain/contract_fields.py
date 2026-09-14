from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

FieldType = Literal["text", "textarea", "number", "amount", "date", "select", "boolean"]


class ContractFieldCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="自定义要素", min_length=1, max_length=64)
    data_type: FieldType = "text"
    required: bool = False
    active: bool = True
    default_value: str = Field(default="", max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=100)
    source_path: str = Field(default="manual", max_length=200)
    sort_order: int = Field(default=100, ge=0, le=9999)

    @field_validator("options")
    @classmethod
    def clean_options(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class ContractFieldUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    data_type: FieldType | None = None
    required: bool | None = None
    active: bool | None = None
    default_value: str | None = Field(default=None, max_length=2000)
    options: list[str] | None = Field(default=None, max_length=100)
    source_path: str | None = Field(default=None, max_length=200)
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class ContractField(ContractFieldCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    created_by: str
    created_at: datetime
