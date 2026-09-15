from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AviationMaterialProfileRecord(Base):
    __tablename__ = "aviation_material_profiles"

    material_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    part_number: Mapped[str] = mapped_column(String(120), index=True)
    oem: Mapped[str] = mapped_column(String(160), default="")
    ata_chapter: Mapped[str] = mapped_column(String(20), default="", index=True)
    applicability: Mapped[str] = mapped_column(String(500), default="")
    serial_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    batch_controlled: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_conditions_json: Mapped[str] = mapped_column(Text, default="[]")
    certificate_requirements_json: Mapped[str] = mapped_column(Text, default="[]")
    trace_required: Mapped[bool] = mapped_column(Boolean, default=True)
    shelf_life_days: Mapped[int] = mapped_column(Integer, default=0)
    life_limited: Mapped[bool] = mapped_column(Boolean, default=False)
    minimum_remaining_life: Mapped[str] = mapped_column(String(120), default="")
    default_offer_type: Mapped[str] = mapped_column(String(24), default="purchase")
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AviationSupplierCapabilityRecord(Base):
    __tablename__ = "aviation_supplier_capabilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    supplier_id: Mapped[str] = mapped_column(String(36), index=True)
    capability_name: Mapped[str] = mapped_column(String(160), index=True)
    supplier_type: Mapped[str] = mapped_column(String(32), default="distributor", index=True)
    oem_scope: Mapped[str] = mapped_column(String(500), default="")
    part_scope: Mapped[str] = mapped_column(String(1000), default="")
    offer_types_json: Mapped[str] = mapped_column(Text, default="[]")
    certificates_json: Mapped[str] = mapped_column(Text, default="[]")
    aog_247: Mapped[bool] = mapped_column(Boolean, default=False)
    response_hours: Mapped[int] = mapped_column(Integer, default=24)
    public_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    relationship_status: Mapped[str] = mapped_column(String(32), default="not_verified", index=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AviationRequisitionProfileRecord(Base):
    __tablename__ = "aviation_requisition_profiles"

    requisition_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    demand_type: Mapped[str] = mapped_column(String(24), default="planned", index=True)
    aircraft_registration: Mapped[str] = mapped_column(String(40), default="")
    work_package: Mapped[str] = mapped_column(String(100), default="")
    finding_no: Mapped[str] = mapped_column(String(80), default="")
    required_within_hours: Mapped[int] = mapped_column(Integer, default=0)
    grounded: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_channel: Mapped[str] = mapped_column(String(80), default="normal")
    maximum_premium_percent: Mapped[int] = mapped_column(Integer, default=0)
    evidence: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AviationMaterialProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    part_number: str = Field(min_length=2, max_length=120)
    oem: str = Field(default="", max_length=160)
    ata_chapter: str = Field(default="", max_length=20)
    applicability: str = Field(default="", max_length=500)
    serial_controlled: bool = False
    batch_controlled: bool = True
    allowed_conditions: list[str] = Field(default_factory=lambda: ["NEW"], max_length=10)
    certificate_requirements: list[str] = Field(default_factory=list, max_length=20)
    trace_required: bool = True
    shelf_life_days: int = Field(default=0, ge=0, le=36500)
    life_limited: bool = False
    minimum_remaining_life: str = Field(default="", max_length=120)
    default_offer_type: str = Field(default="purchase", pattern="^(purchase|exchange|loan|repair)$")
    note: str = Field(default="", max_length=2000)


class AviationSupplierCapability(BaseModel):
    capability_name: str = Field(min_length=2, max_length=160)
    supplier_type: str = Field(
        default="distributor",
        pattern="^(oem|authorized_distributor|distributor|repair_station|trader|pool)$",
    )
    oem_scope: str = Field(default="", max_length=500)
    part_scope: str = Field(default="", max_length=1000)
    offer_types: list[str] = Field(default_factory=list, max_length=10)
    certificates: list[str] = Field(default_factory=list, max_length=20)
    aog_247: bool = False
    response_hours: int = Field(default=24, ge=1, le=720)
    public_reference: bool = False
    relationship_status: str = Field(
        default="not_verified", pattern="^(not_verified|candidate|qualified|suspended)$"
    )
    evidence: str = Field(default="", max_length=2000)


class AviationRequisitionProfile(BaseModel):
    demand_type: str = Field(default="planned", pattern="^(planned|non_routine|aog)$")
    aircraft_registration: str = Field(default="", max_length=40)
    work_package: str = Field(default="", max_length=100)
    finding_no: str = Field(default="", max_length=80)
    required_within_hours: int = Field(default=0, ge=0, le=8760)
    grounded: bool = False
    approval_channel: str = Field(default="normal", max_length=80)
    maximum_premium_percent: int = Field(default=0, ge=0, le=500)
    evidence: str = Field(default="", max_length=2000)
