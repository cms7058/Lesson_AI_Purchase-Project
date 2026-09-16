import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.mro_intelligence import (
    MroAnalyzeRequest,
    MroDemandEventRecord,
    MroIngestRequest,
    MroLeadTimeRecord,
    MroMaterialProfile,
    MroMaterialProfileRecord,
    MroPlanExecutionRecord,
    MroPlanningRunRecord,
    MroSupplyPositionRecord,
)
from app.domain.persistence import MaterialRecord
from app.domain.orders import OrderLineInput, PurchaseOrderCreate
from app.domain.spare_operations import (
    WarehouseLocationRecord,
    WarehousePickingTaskRecord,
    WarehouseRecord,
)
from app.services.audit_service import write_audit_log
from app.services.mro_intelligence import analyze, profile_view, save_run
from app.services.order_service import order_service

router = APIRouter(prefix="/mro-intelligence", tags=["mro-intelligence"])
MANAGERS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}


def require_manager(user: CurrentUser):
    if user.role not in MANAGERS:
        raise HTTPException(403, "当前角色无权维护MRO画像与计划")


POSITION_NAMES = {
    "owned": "自有库存",
    "consignment": "寄售库存",
    "vmi": "VMI库存",
    "in_transit": "在途库存",
    "repair_return": "修理回转库",
    "pool": "共享库存池",
}


class InventoryStatusRequest(BaseModel):
    material_codes: list[str] = Field(min_length=1, max_length=100)
    plan_run_id: str = Field(default="", max_length=36)


class PlanExecutionRequest(BaseModel):
    plan_run_id: str = Field(default="", max_length=36)
    plan_event_id: str = Field(min_length=1, max_length=100)
    material_code: str = Field(min_length=1, max_length=64)
    material_name: str = Field(default="", max_length=200)
    quantity: float = Field(gt=0)
    plan_date: date | None = None
    action_type: str = Field(pattern="^(activate_supply|create_order)$")


def position_view(row: MroSupplyPositionRecord, today: date) -> dict:
    effective = max(0.0, row.quantity - row.reserved_quantity - row.quarantined_quantity)
    available_now = bool(row.confirmed and (not row.available_date or row.available_date <= today))
    return {
        "id": row.id,
        "warehouse_code": row.warehouse_code,
        "position_type": row.position_type,
        "position_name": POSITION_NAMES.get(row.position_type, row.position_type),
        "quantity": row.quantity,
        "reserved_quantity": row.reserved_quantity,
        "quarantined_quantity": row.quarantined_quantity,
        "effective_quantity": round(effective if available_now else 0, 2),
        "available_date": row.available_date,
        "available_now": available_now,
        "confirmed": row.confirmed,
        "source_system": row.source_system,
    }


def execution_view(row: MroPlanExecutionRecord) -> dict:
    return {
        "id": row.id,
        "plan_run_id": row.plan_run_id,
        "plan_event_id": row.plan_event_id,
        "material_code": row.material_code,
        "action_type": row.action_type,
        "reference_id": row.reference_id,
        "reference_no": row.reference_no,
        "quantity": row.quantity,
        "created_at": row.created_at,
    }


@router.get("/integration-schema")
def integration_schema():
    return {
        "endpoint": "/api/v1/mro-intelligence/ingest",
        "idempotency": "每类数据按 source_system + source_ref 去重",
        "systems": {
            "AMOS": ["维修计划", "非例行任务", "AOG事件", "健康监测", "修理回转"],
            "SAP": ["采购订单", "收货日期", "供应商", "真实交期"],
            "WMS": ["自有库存", "预留", "隔离", "历史领用"],
            "CONSIGNMENT": ["寄售库存", "可用日期", "库存确认状态"],
            "VMI": ["供应商管理库存", "补货在途", "可用日期"],
        },
        "required_fields": {
            "demand_events": [
                "material_code",
                "event_date",
                "quantity",
                "source_system",
                "source_ref",
            ],
            "supply_positions": [
                "material_code",
                "position_type",
                "quantity",
                "source_system",
                "source_ref",
            ],
            "lead_time_samples": [
                "material_code",
                "days",
                "happened_date",
                "source_system",
                "source_ref",
            ],
        },
    }


@router.post("/ingest")
def ingest(
    payload: MroIngestRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    require_manager(user)
    codes = {row.material_code for row in payload.demand_events}
    codes |= {row.material_code for row in payload.supply_positions}
    codes |= {row.material_code for row in payload.lead_time_samples}
    known = (
        set(db.scalars(select(MaterialRecord.code).where(MaterialRecord.code.in_(codes))))
        if codes
        else set()
    )
    unknown = sorted(codes - known)
    if unknown:
        raise HTTPException(422, {"message": "存在未建档物料", "material_codes": unknown})
    accepted = {"demand_events": 0, "supply_positions": 0, "lead_time_samples": 0}
    duplicates = {key: 0 for key in accepted}
    mappings = (
        ("demand_events", payload.demand_events, MroDemandEventRecord),
        ("supply_positions", payload.supply_positions, MroSupplyPositionRecord),
        ("lead_time_samples", payload.lead_time_samples, MroLeadTimeRecord),
    )
    for key, rows, model in mappings:
        for item in rows:
            exists = db.scalar(
                select(model.id).where(
                    model.source_system == item.source_system,
                    model.source_ref == item.source_ref,
                )
            )
            if exists:
                duplicates[key] += 1
                continue
            db.add(model(**item.model_dump()))
            accepted[key] += 1
    write_audit_log(
        db,
        actor_id=user.user_id,
        actor_role=user.role,
        action="ingest",
        resource_type="mro_planning_data",
        resource_id="batch",
        detail=f"MRO标准化数据接收 accepted={accepted} duplicates={duplicates}",
    )
    db.commit()
    return {"accepted": accepted, "duplicates": duplicates, "material_codes": sorted(codes)}


@router.post("/demo")
def create_demo(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_manager(user)
    from app.seed_mro_intelligence_demo import seed

    return {"result": seed(db), "note": "仅新增带【演示】标识的教学数据，不覆盖现有数据"}


@router.get("/profiles")
def list_profiles(
    keyword: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = []
    if keyword:
        filters.append(MroMaterialProfileRecord.material_code.ilike(f"%{keyword.strip()}%"))
    total = (
        db.scalar(select(func.count()).select_from(MroMaterialProfileRecord).where(*filters)) or 0
    )
    rows = list(
        db.scalars(
            select(MroMaterialProfileRecord)
            .where(*filters)
            .order_by(MroMaterialProfileRecord.material_code)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    names = (
        {
            row.code: row.name
            for row in db.scalars(
                select(MaterialRecord).where(
                    MaterialRecord.code.in_([row.material_code for row in rows])
                )
            )
        }
        if rows
        else {}
    )
    return {
        "items": [
            profile_view(row) | {"material_name": names.get(row.material_code, row.material_code)}
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/profiles/{material_code}")
def get_profile(material_code: str, db: Session = Depends(get_db)):
    row = db.get(MroMaterialProfileRecord, material_code)
    return profile_view(row) if row else None


@router.put("/profiles/{material_code}")
def save_profile(
    material_code: str,
    payload: MroMaterialProfile,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    require_manager(user)
    if not db.scalar(select(MaterialRecord.id).where(MaterialRecord.code == material_code)):
        raise HTTPException(404, "物料不存在")
    row = db.get(MroMaterialProfileRecord, material_code)
    if not row:
        row = MroMaterialProfileRecord(material_code=material_code)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.version = (row.version or 0) + 1
    write_audit_log(
        db,
        actor_id=user.user_id,
        actor_role=user.role,
        action="upsert",
        resource_type="mro_material_profile",
        resource_id=material_code,
        detail="维护MRO多维物料画像",
    )
    db.commit()
    db.refresh(row)
    return profile_view(row)


@router.post("/analyze")
def analyze_plan(
    payload: MroAnalyzeRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    result = analyze(db, payload.horizon_days, payload.material_codes)
    if payload.save and result["items"]:
        result["run_id"] = save_run(db, result, payload.material_codes, user.user_id)
    return result


@router.post("/inventory-status")
def inventory_status(payload: InventoryStatusRequest, db: Session = Depends(get_db)):
    today = datetime.now(UTC).date()
    positions = list(
        db.scalars(
            select(MroSupplyPositionRecord)
            .where(MroSupplyPositionRecord.material_code.in_(payload.material_codes))
            .order_by(
                MroSupplyPositionRecord.material_code,
                MroSupplyPositionRecord.position_type,
                MroSupplyPositionRecord.warehouse_code,
            )
        )
    )
    grouped = {code: [] for code in payload.material_codes}
    for row in positions:
        grouped.setdefault(row.material_code, []).append(position_view(row, today))
    execution_query = select(MroPlanExecutionRecord).where(
        MroPlanExecutionRecord.material_code.in_(payload.material_codes)
    )
    if payload.plan_run_id:
        execution_query = execution_query.where(
            MroPlanExecutionRecord.plan_run_id == payload.plan_run_id
        )
    executions = list(db.scalars(execution_query))
    return {
        "items": [
            {
                "material_code": code,
                "positions": grouped.get(code, []),
                "available_quantity": round(
                    sum(item["effective_quantity"] for item in grouped.get(code, [])), 2
                ),
                "executions": [
                    execution_view(row) for row in executions if row.material_code == code
                ],
            }
            for code in payload.material_codes
        ]
    }


@router.post("/execute")
def execute_plan(
    payload: PlanExecutionRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    require_manager(user)
    key = f"{payload.plan_run_id or 'unsaved'}:{payload.plan_event_id}:{payload.action_type}"
    existing = db.scalar(
        select(MroPlanExecutionRecord).where(MroPlanExecutionRecord.idempotency_key == key)
    )
    if existing:
        return {"created": False, "execution": execution_view(existing)}
    material = db.scalar(select(MaterialRecord).where(MaterialRecord.code == payload.material_code))
    if not material:
        raise HTTPException(404, "物料不存在")
    today = datetime.now(UTC).date()
    if payload.action_type == "activate_supply":
        positions = list(
            db.scalars(
                select(MroSupplyPositionRecord)
                .where(
                    MroSupplyPositionRecord.material_code == payload.material_code,
                    MroSupplyPositionRecord.confirmed.is_(True),
                )
                .order_by(MroSupplyPositionRecord.available_date, MroSupplyPositionRecord.id)
            )
        )
        available = [
            (row, max(0.0, row.quantity - row.reserved_quantity - row.quarantined_quantity))
            for row in positions
            if (not row.available_date or row.available_date <= today)
        ]
        if sum(quantity for _, quantity in available) <= 0:
            raise HTTPException(409, "当前各库均无可用库存，请生成采购订单")
        remaining = payload.quantity
        tasks = []
        warehouses = {
            row.code: row
            for row in db.scalars(
                select(WarehouseRecord).where(
                    WarehouseRecord.code.in_([position.warehouse_code for position, _ in available])
                )
            )
        }
        for position, available_quantity in available:
            if remaining <= 0:
                break
            allocated = min(remaining, available_quantity)
            if allocated <= 0:
                continue
            location = db.scalar(
                select(WarehouseLocationRecord).where(
                    WarehouseLocationRecord.warehouse_code == position.warehouse_code,
                    WarehouseLocationRecord.active.is_(True),
                )
            )
            task = WarehousePickingTaskRecord(
                task_no=f"PICK-MRO-{today:%Y%m%d}-{uuid4().hex[:6].upper()}",
                plan_run_id=payload.plan_run_id,
                plan_event_id=payload.plan_event_id,
                material_code=payload.material_code,
                material_name=payload.material_name or material.name,
                warehouse_code=position.warehouse_code,
                warehouse_type=position.position_type,
                location_code=location.code if location else "",
                quantity=Decimal(str(round(allocated, 4))),
                source_system=position.source_system,
                assigned_to=warehouses.get(position.warehouse_code).manager
                if warehouses.get(position.warehouse_code)
                else "",
                created_by=user.user_id,
            )
            db.add(task)
            tasks.append(task)
            remaining -= allocated
        db.flush()
        reference_id = tasks[0].id
        reference_no = "、".join(task.task_no for task in tasks)
        action_quantity = payload.quantity - max(remaining, 0)
    else:
        order = order_service.create_order(
            db,
            PurchaseOrderCreate(
                supplier_id="MRO-AUTO",
                supplier_name="MRO计划自动寻源（待确认供应商）",
                factory_code="MRO",
                currency="CNY",
                payment_terms=f"由MRO采购计划自动生成；计划事件 {payload.plan_event_id}",
                delivery_address="航空维修中心",
                lines=[
                    OrderLineInput(
                        material_code=payload.material_code,
                        material_name=payload.material_name or material.name,
                        specification=material.specification or "",
                        quantity=Decimal(str(payload.quantity)),
                        unit=material.unit or "件",
                        unit_price=Decimal(str(material.standard_price or 0)),
                        delivery_date=payload.plan_date,
                    )
                ],
            ),
            user.user_id,
        )
        reference_id, reference_no, action_quantity = str(order.id), order.order_no, payload.quantity
    execution = MroPlanExecutionRecord(
        idempotency_key=key,
        plan_run_id=payload.plan_run_id,
        plan_event_id=payload.plan_event_id,
        material_code=payload.material_code,
        action_type=payload.action_type,
        reference_id=reference_id,
        reference_no=reference_no,
        quantity=action_quantity,
        created_by=user.user_id,
    )
    db.add(execution)
    write_audit_log(
        db,
        actor_id=user.user_id,
        actor_role=user.role,
        action=payload.action_type,
        resource_type="mro_plan",
        resource_id=payload.plan_event_id,
        detail=f"{payload.material_code} × {action_quantity} → {reference_no}",
    )
    db.commit()
    db.refresh(execution)
    return {"created": True, "execution": execution_view(execution)}


@router.get("/runs")
def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(MroPlanningRunRecord)) or 0
    rows = list(
        db.scalars(
            select(MroPlanningRunRecord)
            .order_by(MroPlanningRunRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": [
            {
                "id": row.id,
                "horizon_days": row.horizon_days,
                "material_codes": json.loads(row.material_codes_json),
                "created_by": row.created_by,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
