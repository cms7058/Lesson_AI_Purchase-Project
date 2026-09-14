import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.equipment_mro import (
    EquipmentBomRecord,
    EquipmentFaultRecord,
    EquipmentRecord,
    MaintenancePlanRecord,
)
from app.domain.persistence import (
    FactoryRecord,
    MaterialRecord,
    PurchaseOrderLineRecord,
    PurchaseOrderRecord,
)
from app.domain.requisitions import RequisitionCreate, RequisitionLine
from app.domain.spare_operations import SpareStockRecord
from app.services.audit_service import write_audit_log
from app.services.numbering import next_sequence
from app.services.requisition_service import requisition_service

router = APIRouter(tags=["equipment-mro"])
EDITORS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}


class EquipmentInput(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=200)
    factory_code: str = Field(min_length=1, max_length=64)
    location: str = Field(default="", max_length=200)
    model: str = Field(default="", max_length=120)
    manufacturer: str = Field(default="", max_length=200)
    serial_no: str = Field(default="", max_length=120)
    commissioned_date: date | None = None
    criticality: str = Field(default="medium", pattern="^(high|medium|low)$")
    status: str = Field(default="running", pattern="^(running|maintenance|stopped|retired)$")
    responsible_person: str = Field(default="", max_length=100)


class BomInput(BaseModel):
    material_id: str
    quantity: Decimal = Field(default=Decimal(1), gt=0)
    replacement_cycle_days: int = Field(default=365, ge=1, le=36500)
    safety_quantity: Decimal = Field(default=Decimal(0), ge=0)
    critical: bool = False
    remark: str = Field(default="", max_length=500)


class PlanInput(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    plan_type: str = Field(default="preventive", pattern="^(preventive|predictive|inspection)$")
    interval_days: int = Field(default=90, ge=1, le=36500)
    next_due_date: date
    material_code: str = Field(default="", max_length=64)
    planned_quantity: Decimal = Field(default=Decimal(0), ge=0)
    status: str = Field(default="active", pattern="^(active|paused|completed)$")
    owner: str = Field(default="", max_length=100)


class FaultInput(BaseModel):
    occurred_at: datetime
    restored_at: datetime | None = None
    fault_category: str = Field(default="", max_length=100)
    cause: str = Field(default="", max_length=2000)
    action: str = Field(default="", max_length=2000)
    material_code: str = Field(default="", max_length=64)
    quantity_used: Decimal = Field(default=Decimal(0), ge=0)
    status: str = Field(default="open", pattern="^(open|closed)$")
    reported_by: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def dates_valid(self):
        if self.restored_at and self.restored_at < self.occurred_at:
            raise ValueError("恢复时间不能早于故障时间")
        if self.status == "closed" and not self.restored_at:
            raise ValueError("关闭故障必须填写恢复时间")
        return self


class RequirementInput(BaseModel):
    equipment_id: str
    horizon_days: int = Field(default=90, ge=1, le=730)
    needed_date: date | None = None
    selected_material_codes: list[str] = Field(default_factory=list, max_length=200)


def editor(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in EDITORS:
        raise HTTPException(403, "当前角色无权维护设备与MRO数据")
    return user


def equipment(db: Session, item_id: str) -> EquipmentRecord:
    item = db.get(EquipmentRecord, item_id)
    if not item:
        raise HTTPException(404, "未找到设备")
    return item


def audit(db: Session, user: CurrentUser, action: str, kind: str, item_id: str, detail: str) -> None:
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action=action, resource_type=kind, resource_id=item_id, detail=detail)


def page(db: Session, model, filters: list, page_no: int, page_size: int, order) -> dict:
    total = db.scalar(select(func.count()).select_from(model).where(*filters)) or 0
    rows = list(db.scalars(select(model).where(*filters).order_by(order).offset((page_no - 1) * page_size).limit(page_size)))
    return {"items": rows, "total": total, "page": page_no, "page_size": page_size}


@router.get("/equipment")
def list_equipment(keyword: str = Query("", max_length=100), factory_code: str = "", equipment_status: str = Query("", alias="status"), page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    filters = []
    if keyword:
        term = f"%{keyword.strip()}%"; filters.append(or_(EquipmentRecord.code.ilike(term), EquipmentRecord.name.ilike(term), EquipmentRecord.model.ilike(term)))
    if factory_code: filters.append(EquipmentRecord.factory_code == factory_code)
    if equipment_status: filters.append(EquipmentRecord.status == equipment_status)
    result = page(db, EquipmentRecord, filters, page_no, page_size, EquipmentRecord.created_at.desc())
    result["items"] = [{c: getattr(row, c) for c in ("id", "code", "name", "factory_code", "location", "model", "manufacturer", "serial_no", "commissioned_date", "criticality", "status", "responsible_person", "created_at", "updated_at")} for row in result["items"]]
    return result


@router.post("/equipment", status_code=201)
def create_equipment(payload: EquipmentInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    if db.scalar(select(EquipmentRecord.id).where(EquipmentRecord.code == payload.code.strip())): raise HTTPException(409, "设备编码已存在")
    if not db.scalar(select(FactoryRecord.id).where(FactoryRecord.code == payload.factory_code)): raise HTTPException(422, "工厂编码不存在")
    values = payload.model_dump(); values["code"] = payload.code.strip()
    item = EquipmentRecord(**values, created_by=user.user_id); db.add(item); db.flush(); audit(db, user, "create", "equipment", item.id, f"创建设备 {item.code}"); db.commit(); db.refresh(item); return item


@router.patch("/equipment/{item_id}")
def update_equipment(item_id: str, payload: EquipmentInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    item = equipment(db, item_id)
    if payload.code.strip() != item.code and db.scalar(select(EquipmentRecord.id).where(EquipmentRecord.code == payload.code.strip())): raise HTTPException(409, "设备编码已存在")
    if not db.scalar(select(FactoryRecord.id).where(FactoryRecord.code == payload.factory_code)): raise HTTPException(422, "工厂编码不存在")
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    audit(db, user, "update", "equipment", item.id, f"更新设备 {item.code}")
    db.commit(); db.refresh(item); return item


@router.delete("/equipment/{item_id}", status_code=204)
def delete_equipment(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    item = equipment(db, item_id)
    dependencies = sum((db.scalar(select(func.count()).select_from(model).where(model.equipment_id == item_id)) or 0) for model in (EquipmentBomRecord, MaintenancePlanRecord, EquipmentFaultRecord))
    if dependencies: raise HTTPException(409, "设备已有BOM、维护计划或故障记录，不能删除")
    audit(db, user, "delete", "equipment", item_id, f"删除设备 {item.code}"); db.delete(item); db.commit()


@router.get("/equipment/{equipment_id}/bom")
def list_bom(equipment_id: str, page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    equipment(db, equipment_id); return page(db, EquipmentBomRecord, [EquipmentBomRecord.equipment_id == equipment_id], page_no, page_size, EquipmentBomRecord.material_code)


@router.post("/equipment/{equipment_id}/bom", status_code=201)
def create_bom(equipment_id: str, payload: BomInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    device = equipment(db, equipment_id); material = db.get(MaterialRecord, payload.material_id)
    if not material: raise HTTPException(404, "未找到物料")
    if db.scalar(select(EquipmentBomRecord.id).where(EquipmentBomRecord.equipment_id == equipment_id, EquipmentBomRecord.material_id == material.id)): raise HTTPException(409, "设备BOM已包含该物料")
    item = EquipmentBomRecord(equipment_id=equipment_id, material_id=material.id, material_code=material.code, material_name=material.name, **payload.model_dump(exclude={"material_id"})); db.add(item); db.flush(); audit(db, user, "create", "equipment_bom", item.id, f"{device.code}关联{material.code}"); db.commit(); db.refresh(item); return item


@router.patch("/equipment-bom/{item_id}")
def update_bom(item_id: str, payload: BomInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    item = db.get(EquipmentBomRecord, item_id)
    if not item: raise HTTPException(404, "未找到设备BOM")
    if payload.material_id != item.material_id: raise HTTPException(409, "BOM物料不可直接变更，请删除后重新添加")
    for key, value in payload.model_dump(exclude={"material_id"}).items(): setattr(item, key, value)
    audit(db, user, "update", "equipment_bom", item.id, "更新BOM参数"); db.commit(); db.refresh(item); return item


@router.delete("/equipment-bom/{item_id}", status_code=204)
def delete_bom(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    item = db.get(EquipmentBomRecord, item_id)
    if not item: raise HTTPException(404, "未找到设备BOM")
    audit(db, user, "delete", "equipment_bom", item.id, f"移除{item.material_code}"); db.delete(item); db.commit()


@router.get("/equipment/{equipment_id}/maintenance-plans")
def list_plans(equipment_id: str, page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    equipment(db, equipment_id); return page(db, MaintenancePlanRecord, [MaintenancePlanRecord.equipment_id == equipment_id], page_no, page_size, MaintenancePlanRecord.next_due_date)


@router.post("/equipment/{equipment_id}/maintenance-plans", status_code=201)
def create_plan(equipment_id: str, payload: PlanInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    device = equipment(db, equipment_id)
    if payload.material_code and not db.scalar(select(MaterialRecord.id).where(MaterialRecord.code == payload.material_code)): raise HTTPException(422, "维护计划物料编码不存在")
    item = MaintenancePlanRecord(equipment_id=equipment_id, **payload.model_dump()); db.add(item); db.flush(); audit(db, user, "create", "maintenance_plan", item.id, f"{device.code} {item.name}"); db.commit(); db.refresh(item); return item


@router.patch("/maintenance-plans/{item_id}")
def update_plan(item_id: str, payload: PlanInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    item = db.get(MaintenancePlanRecord, item_id)
    if not item: raise HTTPException(404, "未找到维护计划")
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    audit(db, user, "update", "maintenance_plan", item.id, "更新维护计划"); db.commit(); db.refresh(item); return item


@router.delete("/maintenance-plans/{item_id}", status_code=204)
def delete_plan(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    item = db.get(MaintenancePlanRecord, item_id)
    if not item: raise HTTPException(404, "未找到维护计划")
    audit(db, user, "delete", "maintenance_plan", item.id, item.name); db.delete(item); db.commit()


def fault_view(item: EquipmentFaultRecord) -> dict:
    return {key: getattr(item, key) for key in ("id", "equipment_id", "fault_no", "occurred_at", "restored_at", "downtime_hours", "fault_category", "cause", "action", "material_code", "quantity_used", "status", "reported_by", "created_at")}


@router.get("/equipment/{equipment_id}/faults")
def list_faults(equipment_id: str, page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    equipment(db, equipment_id); result = page(db, EquipmentFaultRecord, [EquipmentFaultRecord.equipment_id == equipment_id], page_no, page_size, EquipmentFaultRecord.occurred_at.desc()); result["items"] = [fault_view(i) for i in result["items"]]; return result


def set_fault(item: EquipmentFaultRecord, payload: FaultInput) -> None:
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    item.downtime_hours = Decimal(str(round(max(0, ((payload.restored_at - payload.occurred_at).total_seconds() / 3600) if payload.restored_at else 0), 2)))


@router.post("/equipment/{equipment_id}/faults", status_code=201)
def create_fault(equipment_id: str, payload: FaultInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    device = equipment(db, equipment_id)
    if payload.material_code and not db.scalar(select(MaterialRecord.id).where(MaterialRecord.code == payload.material_code)): raise HTTPException(422, "故障更换物料编码不存在")
    sequence = next_sequence(db, EquipmentFaultRecord, "fault_no", "FLT") + 1
    item = EquipmentFaultRecord(equipment_id=equipment_id, fault_no=f"FLT-{sequence:06d}", occurred_at=payload.occurred_at); set_fault(item, payload); db.add(item); db.flush(); audit(db, user, "create", "equipment_fault", item.id, f"{device.code} {item.fault_no}"); db.commit(); db.refresh(item); return fault_view(item)


@router.patch("/equipment-faults/{item_id}")
def update_fault(item_id: str, payload: FaultInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    item = db.get(EquipmentFaultRecord, item_id)
    if not item: raise HTTPException(404, "未找到故障记录")
    if payload.material_code and not db.scalar(select(MaterialRecord.id).where(MaterialRecord.code == payload.material_code)): raise HTTPException(422, "故障更换物料编码不存在")
    set_fault(item, payload); audit(db, user, "update", "equipment_fault", item.id, "更新故障与修复记录"); db.commit(); db.refresh(item); return fault_view(item)


@router.delete("/equipment-faults/{item_id}", status_code=204)
def delete_fault(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    item = db.get(EquipmentFaultRecord, item_id)
    if not item: raise HTTPException(404, "未找到故障记录")
    audit(db, user, "delete", "equipment_fault", item.id, item.fault_no); db.delete(item); db.commit()


def mtbf(db: Session, equipment_id: str) -> dict:
    faults = list(db.scalars(select(EquipmentFaultRecord).where(EquipmentFaultRecord.equipment_id == equipment_id, EquipmentFaultRecord.status == "closed").order_by(EquipmentFaultRecord.occurred_at)))
    intervals = [round((faults[index].occurred_at - faults[index - 1].occurred_at).total_seconds() / 3600, 2) for index in range(1, len(faults))]
    value = round(sum(intervals) / len(intervals), 2) if intervals else None
    return {"failure_count": len(faults), "mtbf_hours": value, "intervals": [{"from": faults[i - 1].fault_no, "to": faults[i].fault_no, "hours": intervals[i - 1]} for i in range(1, len(faults))], "method": "相邻已关闭故障发生时间间隔的算术平均；少于2次故障不输出MTBF"}


@router.get("/equipment/{equipment_id}/reliability")
def reliability(equipment_id: str, db: Session = Depends(get_db)):
    device = equipment(db, equipment_id); return {"equipment": {"id": device.id, "code": device.code, "name": device.name}, **mtbf(db, equipment_id)}


def analyze_requirement(db: Session, payload: RequirementInput) -> dict:
    device = equipment(db, payload.equipment_id); today = datetime.now().astimezone().date(); end = today + timedelta(days=payload.horizon_days)
    bom = list(db.scalars(select(EquipmentBomRecord).where(EquipmentBomRecord.equipment_id == device.id)))
    plans = list(db.scalars(select(MaintenancePlanRecord).where(MaintenancePlanRecord.equipment_id == device.id, MaintenancePlanRecord.status == "active", MaintenancePlanRecord.next_due_date <= end)))
    reliability_data = mtbf(db, device.id); equipment_mtbf = reliability_data["mtbf_hours"]
    rows, warnings = [], []
    for line in bom:
        material = db.get(MaterialRecord, line.material_id)
        planned = sum(float(p.planned_quantity) for p in plans if p.material_code == line.material_code)
        lifecycle = math.ceil(payload.horizon_days / line.replacement_cycle_days) * float(line.quantity) if not planned else 0
        material_faults = list(db.scalars(select(EquipmentFaultRecord).where(EquipmentFaultRecord.equipment_id == device.id, EquipmentFaultRecord.status == "closed", EquipmentFaultRecord.material_code == line.material_code)))
        average_used = sum(float(f.quantity_used) for f in material_faults) / len(material_faults) if material_faults else float(line.quantity)
        corrective = round(payload.horizon_days * 24 / equipment_mtbf * average_used, 2) if equipment_mtbf else 0
        available = float(db.scalar(select(func.sum(SpareStockRecord.quantity - SpareStockRecord.planned_reserve)).where(SpareStockRecord.material_code == line.material_code, SpareStockRecord.lifecycle_status == "in_stock", SpareStockRecord.condition == "good")) or 0)
        in_transit = float(db.scalar(select(func.sum(PurchaseOrderLineRecord.quantity)).join(PurchaseOrderRecord, PurchaseOrderLineRecord.order_id == PurchaseOrderRecord.id).where(PurchaseOrderLineRecord.material_code == line.material_code, PurchaseOrderRecord.status.in_(["sent", "supplier_confirmed", "partially_delivered", "quality_tracking"]))) or 0)
        gross, safety = round(planned + lifecycle + corrective, 2), float(line.safety_quantity)
        net = max(0, round(gross + safety - available - in_transit, 2))
        rows.append({"material_id": line.material_id, "material_code": line.material_code, "material_name": line.material_name, "unit": material.unit if material else "件", "planned_demand": round(planned + lifecycle, 2), "corrective_demand": corrective, "gross_demand": gross, "safety_quantity": safety, "available_stock": round(available, 2), "in_transit": round(in_transit, 2), "net_requirement": net, "estimated_unit_price": float(material.standard_price) if material else 0, "evidence": {"replacement_cycle_days": line.replacement_cycle_days, "bom_quantity": float(line.quantity), "closed_faults": len(material_faults), "mtbf_hours": equipment_mtbf}})
    if not bom: warnings.append("设备BOM为空，无法计算备件净需求")
    if not equipment_mtbf: warnings.append("已关闭故障少于2次，纠正性需求暂按0计算；请补充历史故障数据")
    return {"equipment": {"id": device.id, "code": device.code, "name": device.name, "factory_code": device.factory_code}, "horizon_days": payload.horizon_days, "horizon_end": end, "reliability": reliability_data, "items": rows, "warnings": warnings, "formula": "净需求=max(0, 计划/周期需求 + MTBF纠正性需求 + 安全数量 - 良品可用库存 - 已确认在途)"}


@router.post("/mro-net-requirements/analyze")
def analyze(payload: RequirementInput, db: Session = Depends(get_db)):
    return analyze_requirement(db, payload)


@router.post("/mro-net-requirements/create-requisition", status_code=201)
def create_requirement_requisition(payload: RequirementInput, db: Session = Depends(get_db), user: CurrentUser = Depends(editor)):
    result = analyze_requirement(db, payload); selected = set(payload.selected_material_codes); rows = [row for row in result["items"] if row["net_requirement"] > 0 and (not selected or row["material_code"] in selected)]
    if not rows: raise HTTPException(409, "当前测算没有大于0的可转采购净需求")
    request = requisition_service.create(db, RequisitionCreate(title=f"{result['equipment']['code']} MRO净需求采购申请", factory_code=result["equipment"]["factory_code"], department="设备维修", priority="high", needed_date=payload.needed_date or datetime.now().astimezone().date() + timedelta(days=min(payload.horizon_days, 30)), reason=f"由设备BOM、维护计划、故障MTBF、库存及在途自动测算。{result['formula']}", lines=[RequisitionLine(material_code=row["material_code"], material_name=row["material_name"], quantity=Decimal(str(row["net_requirement"])), unit=row["unit"], estimated_unit_price=Decimal(str(row["estimated_unit_price"]))) for row in rows]), user.user_id)
    audit(db, user, "create", "purchase_requisition", str(request.id), f"由设备 {result['equipment']['code']} MRO净需求生成 {request.request_no}"); db.commit(); return {"requisition": request, "analysis": result}
