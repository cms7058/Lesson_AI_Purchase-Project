from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EquipmentRecord(Base):
    __tablename__ = "mro_equipment"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    factory_code: Mapped[str] = mapped_column(String(64), index=True)
    location: Mapped[str] = mapped_column(String(200), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    manufacturer: Mapped[str] = mapped_column(String(200), default="")
    serial_no: Mapped[str] = mapped_column(String(120), default="")
    commissioned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    criticality: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    responsible_person: Mapped[str] = mapped_column(String(100), default="")
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EquipmentBomRecord(Base):
    __tablename__ = "mro_equipment_bom"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    equipment_id: Mapped[str] = mapped_column(String(36), index=True)
    material_id: Mapped[str] = mapped_column(String(36), index=True)
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    material_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(1))
    replacement_cycle_days: Mapped[int] = mapped_column(Integer, default=365)
    safety_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    remark: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaintenancePlanRecord(Base):
    __tablename__ = "mro_maintenance_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    equipment_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    plan_type: Mapped[str] = mapped_column(String(24), default="preventive", index=True)
    interval_days: Mapped[int] = mapped_column(Integer, default=90)
    next_due_date: Mapped[date] = mapped_column(Date, index=True)
    material_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    owner: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EquipmentFaultRecord(Base):
    __tablename__ = "mro_equipment_faults"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    equipment_id: Mapped[str] = mapped_column(String(36), index=True)
    fault_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    downtime_hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))
    fault_category: Mapped[str] = mapped_column(String(100), default="")
    cause: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    material_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    quantity_used: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    reported_by: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
