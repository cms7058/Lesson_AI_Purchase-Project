from datetime import date
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SparePlanRecord(Base):
    __tablename__ = 'spare_purchase_plans'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)


class SpareScenario(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=0, le=1000000)
    unit_price: float = Field(ge=0, le=1e9, allow_inf_nan=False)
    arrival: date
    fees: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    holding: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    quality_loss: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    downtime_loss: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    emergency_loss: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    obsolescence_loss: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    risk_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    evidence: str = Field(min_length=1, max_length=2000)


class SparePlanInput(BaseModel):
    material_code: str = Field(min_length=1, max_length=64)
    abc: Literal['A','B','C'] = 'B'
    ved: Literal['V','E','D'] = 'E'
    fsn: Literal['F','S','N'] = 'S'
    classification_reason: str = Field(min_length=1, max_length=2000)
    currency: str = Field(default='CNY', pattern='^[A-Z]{3}$')
    as_of: date
    required_date: date
    horizon_end: date
    demand: int = Field(ge=0, le=1000000)
    available: int = Field(default=0, ge=0, le=1000000)
    confirmed_inbound: int = Field(default=0, ge=0, le=1000000)
    reserve: int = Field(default=0, ge=0, le=1000000)
    budget: float = Field(ge=0, le=1e15, allow_inf_nan=False)
    risk_limit_v: float = Field(ge=0, le=100, allow_inf_nan=False)
    risk_limit_e: float = Field(ge=0, le=100, allow_inf_nan=False)
    risk_limit_d: float = Field(ge=0, le=100, allow_inf_nan=False)
    data_source: str = Field(min_length=1, max_length=2000)
    scenarios: list[SpareScenario] = Field(min_length=2, max_length=30)
    version: int = Field(default=1, ge=1)

    @model_validator(mode='after')
    def validate_period(self):
        if not self.risk_limit_v <= self.risk_limit_e <= self.risk_limit_d:
            raise ValueError('风险上限应满足V类≤E类≤D类')
        if not self.as_of <= self.required_date <= self.horizon_end:
            raise ValueError('日期须满足数据时点≤需求日期≤规划期末')
        if any(s.arrival < self.as_of for s in self.scenarios):
            raise ValueError('候选方案到货日期不能早于数据时点')
        if len({s.name for s in self.scenarios}) != len(self.scenarios):
            raise ValueError('候选方案名称不能重复')
        return self
