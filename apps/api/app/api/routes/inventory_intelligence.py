import json
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import pstdev
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.equipment_mro import EquipmentBomRecord, EquipmentFaultRecord, MaintenancePlanRecord
from app.domain.inventory_intelligence import LifecycleCostAnalysisRecord, SupplyCollaborationRecord
from app.domain.material_policy import MaterialPolicy
from app.domain.persistence import MaterialRecord, SupplierRecord
from app.domain.spare_operations import SpareStockRecord, WarehouseMovementRecord
from app.services.audit_service import write_audit_log

router = APIRouter(tags=["inventory-intelligence"])
EDITORS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}


class CollaborationInput(BaseModel):
    material_code: str = Field(min_length=2, max_length=64)
    supplier_code: str = Field(min_length=2, max_length=64)
    supplier_name: str = Field(default="", max_length=200)
    mode: Literal["shared_stock", "vmi", "consignment"]
    ownership: Literal["supplier", "buyer", "shared"] = "supplier"
    replenishment_rule: str = Field(min_length=2, max_length=500)
    settlement_trigger: str = Field(min_length=2, max_length=200)
    min_quantity: Decimal = Field(default=Decimal(0), ge=0)
    max_quantity: Decimal = Field(default=Decimal(0), ge=0)
    response_hours: int = Field(default=24, ge=1, le=8760)
    service_level: Decimal = Field(default=95, ge=50, le=100)
    effective_from: date | None = None
    effective_to: date | None = None
    status: Literal["draft", "active", "paused", "expired"] = "draft"
    evidence: str = Field(min_length=2, max_length=4000)
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def valid_range(self):
        if self.max_quantity and self.max_quantity < self.min_quantity:
            raise ValueError("最高保障数量不能低于最低保障数量")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("协议结束日期不能早于开始日期")
        return self


class IntelligenceInput(BaseModel):
    scenario_name: str = Field(default="基准方案", min_length=2, max_length=160)
    service_level: Literal[90, 95, 97, 99] = 95
    review_days: int = Field(default=30, ge=1, le=365)
    horizon_years: int = Field(default=5, ge=1, le=30)
    unit_price: Decimal | None = Field(default=None, ge=0)
    logistics_cost: Decimal = Field(default=Decimal(0), ge=0)
    annual_maintenance_cost: Decimal = Field(default=Decimal(0), ge=0)
    downtime_cost: Decimal = Field(default=Decimal(0), ge=0)
    disposal_cost: Decimal = Field(default=Decimal(0), ge=0)
    residual_value: Decimal = Field(default=Decimal(0), ge=0)
    annual_holding_rate: Decimal = Field(default=Decimal(18), ge=0, le=100)
    save: bool = False


class ApplyParametersInput(BaseModel):
    stock_ids: list[str] = Field(min_length=1, max_length=100)
    safety_stock: Decimal = Field(ge=0)
    min_stock: Decimal = Field(ge=0)
    reorder_point: Decimal = Field(ge=0)
    max_stock: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if not self.safety_stock <= self.min_stock <= self.reorder_point <= self.max_stock:
            raise ValueError("库存参数必须满足安全库存≤最低库存≤再订货点≤最高库存")
        return self


def editor(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in EDITORS:
        raise HTTPException(403, "当前角色无权维护库存协同与LCC")
    return user


def material(db: Session, code: str) -> MaterialRecord:
    row = db.scalar(select(MaterialRecord).where(MaterialRecord.code == code, MaterialRecord.active.is_(True)))
    if not row:
        raise HTTPException(404, "未找到有效物料")
    return row


def collaboration_refs(db: Session, payload: CollaborationInput) -> tuple[MaterialRecord, SupplierRecord]:
    item = material(db, payload.material_code)
    supplier = db.scalar(select(SupplierRecord).where(SupplierRecord.code == payload.supplier_code))
    if not supplier:
        raise HTTPException(422, "供应商编码不存在")
    return item, supplier


@router.get("/supply-collaborations")
def list_collaborations(keyword: str = "", mode: str = "", page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    filters = []
    if keyword:
        term = f"%{keyword.strip()}%"
        filters.append(or_(SupplyCollaborationRecord.material_code.ilike(term), SupplyCollaborationRecord.supplier_code.ilike(term), SupplyCollaborationRecord.supplier_name.ilike(term)))
    if mode:
        filters.append(SupplyCollaborationRecord.mode == mode)
    total = db.scalar(select(func.count()).select_from(SupplyCollaborationRecord).where(*filters)) or 0
    items = list(db.scalars(select(SupplyCollaborationRecord).where(*filters).order_by(SupplyCollaborationRecord.updated_at.desc()).offset((page_no - 1) * page_size).limit(page_size)))
    return {"items": items, "total": total, "page": page_no, "page_size": page_size}


@router.post("/supply-collaborations", status_code=201)
def create_collaboration(payload: CollaborationInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    _, supplier = collaboration_refs(db, payload)
    values = payload.model_dump(exclude={"version"}); values["supplier_name"] = payload.supplier_name or supplier.name
    row = SupplyCollaborationRecord(**values, created_by=user.user_id); db.add(row); db.flush()
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="create", resource_type="supply_collaboration", resource_id=row.id, detail=f"{row.material_code} {row.mode}")
    db.commit(); db.refresh(row); return row


@router.put("/supply-collaborations/{item_id}")
def update_collaboration(item_id: str, payload: CollaborationInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    row = db.get(SupplyCollaborationRecord, item_id)
    if not row: raise HTTPException(404, "协同协议不存在")
    if row.version != payload.version: raise HTTPException(409, "记录已变化，请刷新后重试")
    _, supplier = collaboration_refs(db, payload)
    for key, value in payload.model_dump(exclude={"version"}).items(): setattr(row, key, value)
    row.supplier_name = payload.supplier_name or supplier.name; row.version += 1
    db.commit(); db.refresh(row); return row


@router.delete("/supply-collaborations/{item_id}", status_code=204)
def delete_collaboration(item_id: str, version: int, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    row = db.get(SupplyCollaborationRecord, item_id)
    if not row: raise HTTPException(404, "协同协议不存在")
    if row.version != version: raise HTTPException(409, "记录已变化，请刷新后重试")
    db.delete(row); db.commit()


def demand_evidence(db: Session, code: str) -> dict:
    since = datetime.now().astimezone() - timedelta(days=365)
    issues = list(db.scalars(select(WarehouseMovementRecord).where(WarehouseMovementRecord.material_code == code, WarehouseMovementRecord.movement_type == "issue", WarehouseMovementRecord.happened_at >= since)))
    faults = list(db.scalars(select(EquipmentFaultRecord).where(EquipmentFaultRecord.material_code == code, EquipmentFaultRecord.status == "closed", EquipmentFaultRecord.occurred_at >= since)))
    plans = list(db.scalars(select(MaintenancePlanRecord).where(MaintenancePlanRecord.material_code == code, MaintenancePlanRecord.status == "active")))
    bom = list(db.scalars(select(EquipmentBomRecord).where(EquipmentBomRecord.material_code == code)))
    actual = sum(float(x.quantity) for x in issues) + sum(float(x.quantity_used) for x in faults)
    planned = sum(float(x.planned_quantity) * max(1, math.floor(365 / x.interval_days)) for x in plans)
    lifecycle = sum(float(x.quantity) * max(1, math.floor(365 / x.replacement_cycle_days)) for x in bom)
    annual = max(actual, planned, lifecycle)
    months = [0.0] * 12
    now = datetime.now().astimezone()
    for row in issues:
        delta = (now.year - row.happened_at.year) * 12 + now.month - row.happened_at.month
        if 0 <= delta < 12: months[11 - delta] += float(row.quantity)
    for row in faults:
        delta = (now.year - row.occurred_at.year) * 12 + now.month - row.occurred_at.month
        if 0 <= delta < 12: months[11 - delta] += float(row.quantity_used)
    return {"annual_demand": round(annual, 2), "actual_consumption": round(actual, 2), "planned_annual": round(planned, 2), "lifecycle_annual": round(lifecycle, 2), "monthly": months, "sample_count": len(issues) + len(faults), "method": "实际领用与故障耗用相加，并与维护计划年化量、设备BOM周期年化量取最大值，避免同一维修需求重复累计"}


def analyze(db: Session, code: str, payload: IntelligenceInput) -> dict:
    item = material(db, code); evidence = demand_evidence(db, code)
    policy_row = db.get(MaterialPolicy, code); policy = json.loads(policy_row.payload) if policy_row else {}
    lead_days = max(1, item.lead_time_days); monthly_mean = evidence["annual_demand"] / 12
    monthly_std = pstdev(evidence["monthly"]) if evidence["sample_count"] >= 2 else math.sqrt(monthly_mean)
    z = {90: 1.282, 95: 1.645, 97: 1.881, 99: 2.326}[payload.service_level]
    lead_months = lead_days / 30
    safety = math.ceil(z * monthly_std * math.sqrt(lead_months))
    reorder = math.ceil(monthly_mean * lead_months + safety)
    minimum = safety
    maximum = max(reorder, math.ceil(reorder + monthly_mean * payload.review_days / 30))
    price = float(payload.unit_price if payload.unit_price is not None else item.standard_price)
    acquisition = round(evidence["annual_demand"] * payload.horizon_years * price, 2)
    holding = round(((minimum + maximum) / 2) * price * float(payload.annual_holding_rate) / 100 * payload.horizon_years, 2)
    parts = {"采购取得": acquisition, "物流与加急": float(payload.logistics_cost), "库存持有": holding, "维护保养": float(payload.annual_maintenance_cost) * payload.horizon_years, "停机损失": float(payload.downtime_cost), "处置成本": float(payload.disposal_cost), "残值抵扣": -float(payload.residual_value)}
    active = list(db.scalars(select(SupplyCollaborationRecord).where(SupplyCollaborationRecord.material_code == code, SupplyCollaborationRecord.status == "active")))
    warnings = []
    if evidence["sample_count"] < 6: warnings.append("有效领用/故障样本少于6条，波动采用泊松近似；建议接入EAM/WMS历史数据后复算")
    if not item.lead_time_days: warnings.append("物料交期为空，当前按1天计算")
    result = {"material": {"code": item.code, "name": item.name, "unit": item.unit, "classification": policy}, "inputs": payload.model_dump(mode="json"), "evidence": evidence, "parameters": {"safety_stock": safety, "min_stock": minimum, "reorder_point": reorder, "max_stock": maximum, "lead_time_days": lead_days, "service_level": payload.service_level}, "lcc": {"parts": parts, "total": round(sum(parts.values()), 2), "horizon_years": payload.horizon_years, "currency": "CNY", "formula": "LCC=采购取得+物流加急+库存持有+维护保养+停机损失+处置成本−残值"}, "collaborations": [{"id": x.id, "mode": x.mode, "supplier_name": x.supplier_name, "ownership": x.ownership, "service_level": float(x.service_level), "response_hours": x.response_hours} for x in active], "warnings": warnings, "rules": {"demand": evidence["method"], "safety": "安全库存=z×月需求标准差×√(交期月数)", "reorder": "再订货点=月均需求×交期月数+安全库存", "max": "最高库存=再订货点+评审周期需求"}}
    return result


@router.post("/inventory-intelligence/{material_code}/analyze")
def analyze_inventory(material_code: str, payload: IntelligenceInput, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    result = analyze(db, material_code, payload)
    if payload.save:
        if user.role not in EDITORS: raise HTTPException(403, "当前角色无权保存LCC分析")
        row = LifecycleCostAnalysisRecord(material_code=material_code, scenario_name=payload.scenario_name, total_cost=Decimal(str(result["lcc"]["total"])), payload=json.dumps(result, ensure_ascii=False), created_by=user.user_id)
        db.add(row); db.commit(); db.refresh(row); result["analysis_id"] = row.id
    return result


@router.get("/inventory-intelligence/{material_code}/history")
def lcc_history(material_code: str, page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    material(db, material_code)
    total = db.scalar(select(func.count()).select_from(LifecycleCostAnalysisRecord).where(LifecycleCostAnalysisRecord.material_code == material_code)) or 0
    rows = list(db.scalars(select(LifecycleCostAnalysisRecord).where(LifecycleCostAnalysisRecord.material_code == material_code).order_by(LifecycleCostAnalysisRecord.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size)))
    return {"items": [{"id": x.id, "scenario_name": x.scenario_name, "total_cost": float(x.total_cost), "created_by": x.created_by, "created_at": x.created_at, "result": json.loads(x.payload)} for x in rows], "total": total, "page": page_no, "page_size": page_size}


@router.post("/inventory-intelligence/{material_code}/apply-parameters")
def apply_parameters(material_code: str, payload: ApplyParametersInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    material(db, material_code); rows = list(db.scalars(select(SpareStockRecord).where(SpareStockRecord.id.in_(payload.stock_ids), SpareStockRecord.material_code == material_code)))
    if len(rows) != len(set(payload.stock_ids)): raise HTTPException(422, "所选库存记录与物料不匹配")
    for row in rows:
        row.safety_stock = payload.safety_stock; row.min_stock = payload.min_stock; row.reorder_point = payload.reorder_point; row.max_stock = payload.max_stock; row.version += 1
    db.commit(); return {"updated": len(rows), "material_code": material_code, "parameters": payload.model_dump(exclude={"stock_ids"})}
