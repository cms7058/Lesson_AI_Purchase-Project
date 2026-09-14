from datetime import date, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplierQualificationRecord(Base):
    __tablename__ = "supplier_qualifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    supplier_id: Mapped[str] = mapped_column(String(36), index=True)
    qualification_type: Mapped[str] = mapped_column(String(100), index=True)
    certificate_no: Mapped[str] = mapped_column(String(120), default="")
    issuing_authority: Mapped[str] = mapped_column(String(200), default="")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    attachment_name: Mapped[str] = mapped_column(String(240), default="")
    attachment_path: Mapped[str] = mapped_column(String(100), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    reviewed_by: Mapped[str] = mapped_column(String(64), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupplierQualificationRevision(Base):
    __tablename__ = "supplier_qualification_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    qualification_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(30))
    snapshot_json: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QualificationInput(BaseModel):
    qualification_type: str = Field(min_length=2, max_length=100)
    certificate_no: str = Field(default="", max_length=120)
    issuing_authority: str = Field(default="", max_length=200)
    valid_from: date | None = None
    expires_on: date | None = None
    review_note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.valid_from and self.expires_on and self.expires_on < self.valid_from:
            raise ValueError("资质到期日不能早于生效日")
        return self


class QualificationDecision(BaseModel):
    status: str = Field(pattern="^(approved|rejected|suspended)$")
    note: str = Field(default="", max_length=1000)


class QualificationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_id: str
    supplier_code: str = ""
    supplier_name: str = ""
    qualification_type: str
    certificate_no: str
    issuing_authority: str
    valid_from: date | None
    expires_on: date | None
    review_status: str
    effective_status: str = "pending"
    days_to_expiry: int | None = None
    review_note: str
    attachment_name: str
    version: int
    created_by: str
    reviewed_by: str
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
