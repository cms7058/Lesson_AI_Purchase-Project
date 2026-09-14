from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplyCollaborationRecord(Base):
    __tablename__ = "inventory_supply_collaborations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    supplier_code: Mapped[str] = mapped_column(String(64), index=True)
    supplier_name: Mapped[str] = mapped_column(String(200), default="")
    mode: Mapped[str] = mapped_column(String(24), index=True)
    ownership: Mapped[str] = mapped_column(String(24), default="supplier")
    replenishment_rule: Mapped[str] = mapped_column(String(500), default="")
    settlement_trigger: Mapped[str] = mapped_column(String(200), default="")
    min_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    max_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    response_hours: Mapped[int] = mapped_column(Integer, default=24)
    service_level: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal(95))
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LifecycleCostAnalysisRecord(Base):
    __tablename__ = "inventory_lcc_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    scenario_name: Mapped[str] = mapped_column(String(160))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    payload: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
