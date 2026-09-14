from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SpareProcurementStrategyRecord(Base):
    __tablename__ = "spare_procurement_strategies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160), index=True)
    material_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_mode: Mapped[str] = mapped_column(String(32), default="oem", index=True)
    supplier_model: Mapped[str] = mapped_column(String(32), default="standard", index=True)
    urgency: Mapped[str] = mapped_column(String(16), default="planned", index=True)
    price_baseline: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    premium_limit: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal(0))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    decision_status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    fallback_plan: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WarehouseRecord(Base):
    __tablename__ = "spare_warehouses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    factory_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    address: Mapped[str] = mapped_column(String(500), default="")
    manager: Mapped[str] = mapped_column(String(100), default="")
    maintenance_distance_m: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WarehouseLocationRecord(Base):
    __tablename__ = "spare_warehouse_locations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    warehouse_code: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    zone_type: Mapped[str] = mapped_column(String(32), default="normal", index=True)
    near_maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    heavy_duty: Mapped[bool] = mapped_column(Boolean, default=False)
    temperature_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    humidity_limit: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal(70))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class SpareStockRecord(Base):
    __tablename__ = "spare_stocks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    warehouse_code: Mapped[str] = mapped_column(String(64), index=True)
    location_code: Mapped[str] = mapped_column(String(64), index=True)
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    material_name: Mapped[str] = mapped_column(String(200), default="")
    batch_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    safety_stock: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    min_stock: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    max_stock: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    planned_reserve: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    condition: Mapped[str] = mapped_column(String(24), default="good", index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(24), default="in_stock", index=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), default="manual")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WarehouseMovementRecord(Base):
    __tablename__ = "spare_warehouse_movements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    movement_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    movement_type: Mapped[str] = mapped_column(String(24), index=True)
    warehouse_code: Mapped[str] = mapped_column(String(64), index=True)
    from_location: Mapped[str] = mapped_column(String(64), default="")
    to_location: Mapped[str] = mapped_column(String(64), default="")
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    material_name: Mapped[str] = mapped_column(String(200), default="")
    batch_no: Mapped[str] = mapped_column(String(64), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    business_no: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="posted", index=True)
    operator: Mapped[str] = mapped_column(String(64), default="system")
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StocktakeRecord(Base):
    __tablename__ = "spare_stocktakes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    stock_id: Mapped[str] = mapped_column(String(36), index=True)
    warehouse_code: Mapped[str] = mapped_column(String(64), index=True)
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    book_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    counted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    variance: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="posted")
    counted_by: Mapped[str] = mapped_column(String(64), default="system")
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SohInspectionRecord(Base):
    __tablename__ = "spare_soh_inspections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    stock_id: Mapped[str] = mapped_column(String(36), index=True)
    rust_score: Mapped[int] = mapped_column(Integer, default=100)
    moisture_score: Mapped[int] = mapped_column(Integer, default=100)
    dust_score: Mapped[int] = mapped_column(Integer, default=100)
    packaging_score: Mapped[int] = mapped_column(Integer, default=100)
    conclusion: Mapped[str] = mapped_column(String(24), default="good", index=True)
    action: Mapped[str] = mapped_column(Text, default="")
    inspected_by: Mapped[str] = mapped_column(String(64), default="system")
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
