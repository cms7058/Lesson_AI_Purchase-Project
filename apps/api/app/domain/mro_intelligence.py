from datetime import date, datetime
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MroMaterialProfileRecord(Base):
    __tablename__ = "mro_material_profiles"

    material_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    demand_characteristic: Mapped[str] = mapped_column(String(32), default="stable", index=True)
    aircraft_impact: Mapped[int] = mapped_column(Integer, default=3)
    supply_risk: Mapped[int] = mapped_column(Integer, default=3)
    lead_time_risk: Mapped[int] = mapped_column(Integer, default=3)
    value_level: Mapped[int] = mapped_column(Integer, default=3)
    substitutability: Mapped[int] = mapped_column(Integer, default=3)
    compliance_risk: Mapped[int] = mapped_column(Integer, default=3)
    repairability: Mapped[int] = mapped_column(Integer, default=1)
    single_source: Mapped[bool] = mapped_column(Boolean, default=False)
    long_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    high_value: Mapped[bool] = mapped_column(Boolean, default=False)
    planned: Mapped[bool] = mapped_column(Boolean, default=True)
    non_routine: Mapped[bool] = mapped_column(Boolean, default=False)
    repairable: Mapped[bool] = mapped_column(Boolean, default=False)
    model_override: Mapped[str] = mapped_column(String(48), default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MroDemandEventRecord(Base):
    __tablename__ = "mro_demand_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[float] = mapped_column(Float)
    demand_type: Mapped[str] = mapped_column(String(32), default="consumption", index=True)
    probability: Mapped[float] = mapped_column(Float, default=1.0)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    source_system: Mapped[str] = mapped_column(String(32), default="WMS", index=True)
    source_ref: Mapped[str] = mapped_column(String(100), default="", index=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MroSupplyPositionRecord(Base):
    __tablename__ = "mro_supply_positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    position_type: Mapped[str] = mapped_column(String(32), index=True)
    warehouse_code: Mapped[str] = mapped_column(String(64), default="")
    quantity: Mapped[float] = mapped_column(Float)
    reserved_quantity: Mapped[float] = mapped_column(Float, default=0)
    quarantined_quantity: Mapped[float] = mapped_column(Float, default=0)
    available_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    source_system: Mapped[str] = mapped_column(String(32), index=True)
    source_ref: Mapped[str] = mapped_column(String(100), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MroLeadTimeRecord(Base):
    __tablename__ = "mro_lead_time_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    supplier_name: Mapped[str] = mapped_column(String(160), default="")
    transaction_type: Mapped[str] = mapped_column(String(32), default="purchase")
    days: Mapped[float] = mapped_column(Float)
    happened_date: Mapped[date] = mapped_column(Date, index=True)
    source_system: Mapped[str] = mapped_column(String(32), default="SAP")
    source_ref: Mapped[str] = mapped_column(String(100), default="", index=True)


class MroPlanningRunRecord(Base):
    __tablename__ = "mro_planning_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    horizon_days: Mapped[int] = mapped_column(Integer)
    material_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    result_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MroPlanExecutionRecord(Base):
    __tablename__ = "mro_plan_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    plan_run_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    plan_event_id: Mapped[str] = mapped_column(String(100), index=True)
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    action_type: Mapped[str] = mapped_column(String(32), index=True)
    reference_id: Mapped[str] = mapped_column(String(64), default="")
    reference_no: Mapped[str] = mapped_column(String(64), default="")
    quantity: Mapped[float] = mapped_column(Float)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MroMaterialProfile(BaseModel):
    demand_characteristic: str = Field(
        default="stable", pattern="^(stable|intermittent|lumpy|planned|non_routine)$"
    )
    aircraft_impact: int = Field(default=3, ge=1, le=5)
    supply_risk: int = Field(default=3, ge=1, le=5)
    lead_time_risk: int = Field(default=3, ge=1, le=5)
    value_level: int = Field(default=3, ge=1, le=5)
    substitutability: int = Field(default=3, ge=1, le=5)
    compliance_risk: int = Field(default=3, ge=1, le=5)
    repairability: int = Field(default=1, ge=1, le=5)
    single_source: bool = False
    long_lead: bool = False
    high_value: bool = False
    planned: bool = True
    non_routine: bool = False
    repairable: bool = False
    model_override: str = Field(default="", max_length=48)
    evidence: str = Field(default="", max_length=2000)


class MroAnalyzeRequest(BaseModel):
    horizon_days: int = Field(default=180, ge=30, le=730)
    material_codes: list[str] = Field(default_factory=list, max_length=200)
    save: bool = True


class MroDemandEventInput(BaseModel):
    material_code: str = Field(min_length=2, max_length=64)
    event_date: date
    quantity: float = Field(gt=0)
    demand_type: str = Field(
        default="consumption", pattern="^(planned|non_routine|aog|consumption|health)$"
    )
    probability: float = Field(default=1, ge=0, le=1)
    confirmed: bool = True
    source_system: str = Field(min_length=2, max_length=32)
    source_ref: str = Field(min_length=2, max_length=100)
    evidence: str = Field(default="", max_length=2000)


class MroSupplyPositionInput(BaseModel):
    material_code: str = Field(min_length=2, max_length=64)
    position_type: str = Field(pattern="^(owned|consignment|vmi|in_transit|repair_return|pool)$")
    warehouse_code: str = Field(default="", max_length=64)
    quantity: float = Field(ge=0)
    reserved_quantity: float = Field(default=0, ge=0)
    quarantined_quantity: float = Field(default=0, ge=0)
    available_date: date | None = None
    confirmed: bool = True
    source_system: str = Field(min_length=2, max_length=32)
    source_ref: str = Field(min_length=2, max_length=100)


class MroLeadTimeInput(BaseModel):
    material_code: str = Field(min_length=2, max_length=64)
    supplier_name: str = Field(default="", max_length=160)
    transaction_type: str = Field(default="purchase", pattern="^(purchase|repair|exchange|loan)$")
    days: float = Field(gt=0, le=3650)
    happened_date: date
    source_system: str = Field(default="SAP", min_length=2, max_length=32)
    source_ref: str = Field(min_length=2, max_length=100)


class MroIngestRequest(BaseModel):
    demand_events: list[MroDemandEventInput] = Field(default_factory=list, max_length=5000)
    supply_positions: list[MroSupplyPositionInput] = Field(default_factory=list, max_length=5000)
    lead_time_samples: list[MroLeadTimeInput] = Field(default_factory=list, max_length=5000)
