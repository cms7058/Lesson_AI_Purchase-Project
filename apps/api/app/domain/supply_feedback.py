from datetime import date, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Boolean, Date, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplyFeedback(Base):
    __tablename__ = "supply_feedback"
    __table_args__ = (UniqueConstraint("connector_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    connector_id: Mapped[str] = mapped_column(String(36), index=True)
    external_id: Mapped[str] = mapped_column(String(100))
    supplier_code: Mapped[str] = mapped_column(String(64), index=True)
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    record_date: Mapped[date] = mapped_column(Date)
    source_system: Mapped[str] = mapped_column(String(30))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FeedbackAccess(Base):
    __tablename__ = "feedback_access"
    connector_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))


class AwardAnalysisSnapshot(Base):
    __tablename__ = "award_analysis_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    rfq_id: Mapped[str] = mapped_column(String(36), index=True)
    quotation_id: Mapped[str] = mapped_column(String(36))
    method: Mapped[str] = mapped_column(String(20))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FeedbackRow(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    external_id: str = Field(min_length=1, max_length=100)
    supplier_code: str = Field(min_length=1, max_length=64)
    material_code: str = Field(min_length=1, max_length=64)
    record_date: date
    metrics_available_date: date | None = None
    unit: str = Field(default="件", min_length=1, max_length=24)
    currency: str = Field(default="CNY", pattern="^[A-Z]{3}$")
    received_quantity: float = Field(gt=0, le=1e9)
    inspected_quantity: float | None = Field(default=None, ge=0, le=1e9)
    accepted_quantity: float | None = Field(default=None, ge=0, le=1e9)
    on_time_quantity: float | None = Field(default=None, ge=0, le=1e9)
    rework_quantity: float | None = Field(default=None, ge=0, le=1e9)
    response_hours: float | None = Field(default=None, ge=0, le=1e6)
    lead_time_days: float | None = Field(default=None, ge=0, le=3650)
    unit_price: float | None = Field(default=None, ge=0, le=1e9)
    tax_rate: float = Field(default=0.13, ge=0, le=1)
    logistics_cost: float = Field(default=0, ge=0, le=1e12)
    rework_cost: float = Field(default=0, ge=0, le=1e12)
    delay_cost: float = Field(default=0, ge=0, le=1e12)
    other_cost: float = Field(default=0, ge=0, le=1e12)
    credit: float = Field(default=0, ge=0, le=1e12)
    costs_confirmed: bool = False

    @model_validator(mode="after")
    def quantities(self):
        if self.metrics_available_date and self.metrics_available_date < self.record_date:
            raise ValueError("指标可用日期不能早于业务日期")
        if self.inspected_quantity is not None and self.inspected_quantity > self.received_quantity:
            raise ValueError("检验数量不能超过收货数量")
        for value in [self.accepted_quantity, self.rework_quantity]:
            if value is not None and (self.inspected_quantity is None or value > self.inspected_quantity):
                raise ValueError("合格/返工数量不能超过检验数量，必须提供检验数量")
        if self.on_time_quantity is not None and self.on_time_quantity > self.received_quantity:
            raise ValueError("准时到货数量不能超过收货数量")
        if self.costs_confirmed and (self.unit_price is None or self.inspected_quantity != self.received_quantity or self.accepted_quantity is None):
            raise ValueError("确认成本必须提供价格、完整批次质检及合格数量")
        base = (self.unit_price or 0)*self.received_quantity*(1+self.tax_rate)
        if self.costs_confirmed and self.credit > base+self.logistics_cost+self.rework_cost+self.delay_cost+self.other_cost:
            raise ValueError("退款不能超过总成本")
        return self


class FeedbackBatch(BaseModel):
    rows: list[FeedbackRow] = Field(min_length=1, max_length=1000)
