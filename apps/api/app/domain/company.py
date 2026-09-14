from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyProfileUpdate(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    short_name: str = Field(default="", max_length=64)
    address: str = Field(default="", max_length=500)
    contact: str = Field(default="", max_length=200)


class CompanyProfile(CompanyProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    logo_path: str
    updated_at: datetime
