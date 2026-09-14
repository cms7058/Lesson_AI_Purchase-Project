from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HistoryPoint(BaseModel):
    period: str = Field(min_length=1, max_length=20)
    quantity: float = Field(ge=0)


class ForecastCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    material_code: str = Field(min_length=1, max_length=64)
    material_name: str = Field(min_length=1, max_length=200)
    history: list[HistoryPoint] = Field(min_length=3, max_length=60)
    horizon: int = Field(default=3, ge=1, le=12)
    safety_stock: float = Field(default=0, ge=0)
    on_hand: float = Field(default=0, ge=0)
    in_transit: float = Field(default=0, ge=0)


class ForecastUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    material_name: str | None = Field(default=None, min_length=1, max_length=200)
    history: list[HistoryPoint] | None = Field(default=None, min_length=3, max_length=60)
    horizon: int | None = Field(default=None, ge=1, le=12)
    safety_stock: float | None = Field(default=None, ge=0)
    on_hand: float | None = Field(default=None, ge=0)
    in_transit: float | None = Field(default=None, ge=0)


class Forecast(ForecastCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    result: dict
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class SourcingCandidate(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=200)
    country: str = Field(default="中国", max_length=80)
    source_url: str = Field(default="", max_length=500)
    capabilities: str = Field(default="", max_length=1000)
    price_score: float = Field(default=80, ge=0, le=100)
    quality_score: float = Field(default=80, ge=0, le=100)
    delivery_score: float = Field(default=80, ge=0, le=100)
    risk_level: str = Field(default="low", pattern="^(low|medium|high)$")


class SourcingCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=1, max_length=120)
    requirements: str = Field(default="", max_length=3000)
    candidates: list[SourcingCandidate] = Field(default_factory=list, max_length=100)


class SourcingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    requirements: str | None = Field(default=None, max_length=3000)
    candidates: list[SourcingCandidate] | None = Field(default=None, max_length=100)


class SourcingProject(SourcingCreate):
    id: UUID
    result: dict
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class SupplyNode(BaseModel):
    supplier: str = Field(min_length=1, max_length=120)
    capacity: float = Field(gt=0)


class DemandNode(BaseModel):
    factory: str = Field(min_length=1, max_length=120)
    quantity: float = Field(gt=0)


class RouteLane(BaseModel):
    supplier: str = Field(min_length=1, max_length=120)
    factory: str = Field(min_length=1, max_length=120)
    unit_cost: float = Field(ge=0)
    lead_days: float = Field(default=0, ge=0)
    risk_score: float = Field(default=0, ge=0, le=100)
    max_quantity: float | None = Field(default=None, gt=0)


class RoutingCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    material_code: str = Field(min_length=1, max_length=64)
    supplies: list[SupplyNode] = Field(min_length=1, max_length=50)
    demands: list[DemandNode] = Field(min_length=1, max_length=50)
    lanes: list[RouteLane] = Field(min_length=1, max_length=500)
    lead_weight: float = Field(default=1, ge=0)
    risk_weight: float = Field(default=1, ge=0)

    @model_validator(mode="after")
    def validate_nodes(self):
        suppliers = {item.supplier for item in self.supplies}
        factories = {item.factory for item in self.demands}
        if any(item.supplier not in suppliers or item.factory not in factories for item in self.lanes):
            raise ValueError("运输线路必须引用已定义的供应商和工厂")
        return self


class RoutingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    supplies: list[SupplyNode] | None = Field(default=None, min_length=1, max_length=50)
    demands: list[DemandNode] | None = Field(default=None, min_length=1, max_length=50)
    lanes: list[RouteLane] | None = Field(default=None, min_length=1, max_length=500)
    lead_weight: float | None = Field(default=None, ge=0)
    risk_weight: float | None = Field(default=None, ge=0)


class RoutingPlan(RoutingCreate):
    id: UUID
    result: dict
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class ReportCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    report_type: str = Field(pattern="^(overview|supplier|quality|contract)$")
    notes: str = Field(default="", max_length=3000)


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    report_type: str | None = Field(default=None, pattern="^(overview|supplier|quality|contract)$")
    notes: str | None = Field(default=None, max_length=3000)


class ProcurementReport(ReportCreate):
    id: UUID
    content: dict
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
