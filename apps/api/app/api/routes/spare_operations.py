from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.persistence import MaterialRecord
from app.domain.spare_operations import (
    SohInspectionRecord,
    SpareProcurementStrategyRecord,
    SpareStockRecord,
    StocktakeRecord,
    WarehouseLocationRecord,
    WarehouseMovementRecord,
    WarehouseRecord,
)

router = APIRouter(tags=["spare-operations"])
EDITORS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}


def require_editor(user: CurrentUser):
    if user.role not in EDITORS:
        raise HTTPException(403, "当前角色无权维护备件采购与仓储数据")


def page(db, model, page, page_size, clause=None, ordering=None):
    query = select(model)
    count = select(func.count()).select_from(model)
    if clause is not None:
        query, count = query.where(clause), count.where(clause)
    total = db.scalar(count) or 0
    rows = db.scalars(query.order_by(model.id if ordering is None else ordering).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": rows, "page": page, "page_size": page_size, "total": total}


class StrategyIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    material_code: str = Field(default="", max_length=64)
    source_mode: Literal["oem", "domestic", "alternative", "remanufactured", "platform", "shared_stock"] = "oem"
    supplier_model: Literal["standard", "consignment", "vmi", "framework", "platform"] = "standard"
    urgency: Literal["planned", "urgent", "shutdown"] = "planned"
    price_baseline: Decimal = Field(default=0, ge=0)
    premium_limit: Decimal = Field(default=0, ge=0, le=500)
    lead_time_days: int = Field(default=0, ge=0, le=3650)
    decision_status: Literal["draft", "reviewing", "approved", "retired"] = "draft"
    rationale: str = Field(min_length=1, max_length=4000)
    fallback_plan: str = Field(default="", max_length=4000)
    version: int = Field(default=1, ge=1)


@router.get("/spare-strategies")
def list_strategies(keyword: str = "", source_mode: str = "", urgency: str = "", page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    clauses = []
    if keyword:
        clauses.append(or_(SpareProcurementStrategyRecord.name.contains(keyword, autoescape=True), SpareProcurementStrategyRecord.material_code.contains(keyword, autoescape=True)))
    if source_mode:
        clauses.append(SpareProcurementStrategyRecord.source_mode == source_mode)
    if urgency:
        clauses.append(SpareProcurementStrategyRecord.urgency == urgency)
    clause = None
    for item in clauses:
        clause = item if clause is None else clause & item
    return page(db, SpareProcurementStrategyRecord, page_no, page_size, clause, SpareProcurementStrategyRecord.updated_at.desc())


@router.post("/spare-strategies", status_code=201)
def create_strategy(payload: StrategyIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user)
    values = payload.model_dump(exclude={"version"})
    if payload.material_code and not db.scalar(select(MaterialRecord.id).where(MaterialRecord.code == payload.material_code, MaterialRecord.active.is_(True))):
        raise HTTPException(422, "物料编码不存在或已停用")
    row = SpareProcurementStrategyRecord(**values, created_by=user.user_id)
    db.add(row); db.commit(); db.refresh(row); return row


@router.put("/spare-strategies/{item_id}")
def update_strategy(item_id: str, payload: StrategyIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); row = db.get(SpareProcurementStrategyRecord, item_id)
    if not row: raise HTTPException(404, "采购策略不存在")
    if row.version != payload.version: raise HTTPException(409, "记录已变化，请刷新后重试")
    for key, value in payload.model_dump(exclude={"version"}).items(): setattr(row, key, value)
    row.version += 1; db.commit(); db.refresh(row); return row


@router.delete("/spare-strategies/{item_id}", status_code=204)
def delete_strategy(item_id: str, version: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); row = db.get(SpareProcurementStrategyRecord, item_id)
    if not row: raise HTTPException(404, "采购策略不存在")
    if row.version != version: raise HTTPException(409, "记录已变化，请刷新后重试")
    db.delete(row); db.commit()


class WarehouseIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    factory_code: str = Field(default="", max_length=64)
    address: str = Field(default="", max_length=500)
    manager: str = Field(default="", max_length=100)
    maintenance_distance_m: Decimal = Field(default=Decimal(0), ge=0)
    active: bool = True
    version: int = Field(default=1, ge=1)


@router.get("/warehouses")
def list_warehouses(keyword: str = "", page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    clause = or_(WarehouseRecord.code.contains(keyword, autoescape=True), WarehouseRecord.name.contains(keyword, autoescape=True))
    return page(db, WarehouseRecord, page_no, page_size, clause, WarehouseRecord.code)


@router.post("/warehouses", status_code=201)
def create_warehouse(payload: WarehouseIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user)
    if db.scalar(select(WarehouseRecord.id).where(WarehouseRecord.code == payload.code)): raise HTTPException(409, "仓库编码已存在")
    row = WarehouseRecord(**payload.model_dump(exclude={"version"})); db.add(row); db.commit(); db.refresh(row); return row


@router.put("/warehouses/{item_id}")
def update_warehouse(item_id: str, payload: WarehouseIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); row = db.get(WarehouseRecord, item_id)
    if not row: raise HTTPException(404, "仓库不存在")
    if row.version != payload.version: raise HTTPException(409, "记录已变化，请刷新后重试")
    if db.scalar(select(WarehouseRecord.id).where(WarehouseRecord.code == payload.code, WarehouseRecord.id != item_id)): raise HTTPException(409, "仓库编码已存在")
    for key, value in payload.model_dump(exclude={"version"}).items(): setattr(row, key, value)
    row.version += 1; db.commit(); db.refresh(row); return row


@router.delete("/warehouses/{item_id}", status_code=204)
def delete_warehouse(item_id: str, version: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); row = db.get(WarehouseRecord, item_id)
    if not row: raise HTTPException(404, "仓库不存在")
    if row.version != version: raise HTTPException(409, "记录已变化，请刷新后重试")
    if db.scalar(select(WarehouseLocationRecord.id).where(WarehouseLocationRecord.warehouse_code == row.code)): raise HTTPException(409, "仓库已有库位，不能删除")
    db.delete(row); db.commit()


class LocationIn(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=160)
    zone_type: Literal["fast", "normal", "heavy", "critical", "quarantine"] = "normal"
    near_maintenance: bool = False
    heavy_duty: bool = False
    temperature_controlled: bool = False
    humidity_limit: Decimal = Field(default=Decimal(70), ge=0, le=100)
    active: bool = True
    version: int = Field(default=1, ge=1)


@router.get("/warehouse-locations")
def list_locations(keyword: str = "", warehouse_code: str = "", page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    clause = or_(WarehouseLocationRecord.code.contains(keyword, autoescape=True), WarehouseLocationRecord.name.contains(keyword, autoescape=True))
    if warehouse_code: clause &= WarehouseLocationRecord.warehouse_code == warehouse_code
    return page(db, WarehouseLocationRecord, page_no, page_size, clause, WarehouseLocationRecord.code)


@router.post("/warehouse-locations", status_code=201)
def create_location(payload: LocationIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user)
    if not db.scalar(select(WarehouseRecord.id).where(WarehouseRecord.code == payload.warehouse_code, WarehouseRecord.active.is_(True))): raise HTTPException(422, "请选择有效仓库")
    if db.scalar(select(WarehouseLocationRecord.id).where(WarehouseLocationRecord.warehouse_code == payload.warehouse_code, WarehouseLocationRecord.code == payload.code)): raise HTTPException(409, "该仓库下库位编码已存在")
    row = WarehouseLocationRecord(**payload.model_dump(exclude={"version"})); db.add(row); db.commit(); db.refresh(row); return row


@router.put("/warehouse-locations/{item_id}")
def update_location(item_id: str, payload: LocationIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); row = db.get(WarehouseLocationRecord, item_id)
    if not row: raise HTTPException(404, "库位不存在")
    if row.version != payload.version: raise HTTPException(409, "记录已变化，请刷新后重试")
    for key, value in payload.model_dump(exclude={"version"}).items(): setattr(row, key, value)
    row.version += 1; db.commit(); db.refresh(row); return row


@router.delete("/warehouse-locations/{item_id}", status_code=204)
def delete_location(item_id: str, version: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); row = db.get(WarehouseLocationRecord, item_id)
    if not row: raise HTTPException(404, "库位不存在")
    if row.version != version: raise HTTPException(409, "记录已变化，请刷新后重试")
    if db.scalar(select(SpareStockRecord.id).where(SpareStockRecord.warehouse_code == row.warehouse_code, SpareStockRecord.location_code == row.code, SpareStockRecord.quantity != 0)): raise HTTPException(409, "库位仍有库存，不能删除")
    db.delete(row); db.commit()


class StockIn(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=64)
    location_code: str = Field(min_length=1, max_length=64)
    material_code: str = Field(min_length=1, max_length=64)
    material_name: str = Field(default="", max_length=200)
    batch_no: str = Field(default="", max_length=64)
    quantity: Decimal = Field(default=Decimal(0), ge=0)
    safety_stock: Decimal = Field(default=Decimal(0), ge=0)
    min_stock: Decimal = Field(default=Decimal(0), ge=0)
    max_stock: Decimal = Field(default=Decimal(0), ge=0)
    reorder_point: Decimal = Field(default=Decimal(0), ge=0)
    planned_reserve: Decimal = Field(default=Decimal(0), ge=0)
    condition: Literal["good", "attention", "quarantine", "damaged"] = "good"
    lifecycle_status: Literal["in_stock", "reserved", "issued", "scrapped", "recycled"] = "in_stock"
    received_date: date | None = None
    last_issue_date: date | None = None
    expiry_date: date | None = None
    source_system: str = Field(default="manual", max_length=64)
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_policy(self):
        if not self.safety_stock <= self.min_stock <= self.reorder_point <= self.max_stock and self.max_stock > 0:
            raise ValueError("库存参数应满足安全库存≤最低库存≤再订货点≤最高库存")
        return self


@router.get("/spare-stocks")
def list_stocks(keyword: str = "", warehouse_code: str = "", condition: str = "", alert_only: bool = False, page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    clause = or_(SpareStockRecord.material_code.contains(keyword, autoescape=True), SpareStockRecord.material_name.contains(keyword, autoescape=True), SpareStockRecord.batch_no.contains(keyword, autoescape=True))
    if warehouse_code: clause &= SpareStockRecord.warehouse_code == warehouse_code
    if condition: clause &= SpareStockRecord.condition == condition
    if alert_only: clause &= or_(SpareStockRecord.quantity <= SpareStockRecord.reorder_point, SpareStockRecord.condition != "good")
    return page(db, SpareStockRecord, page_no, page_size, clause, SpareStockRecord.updated_at.desc())


def validate_stock_refs(db, payload):
    if not db.scalar(select(WarehouseLocationRecord.id).where(WarehouseLocationRecord.warehouse_code == payload.warehouse_code, WarehouseLocationRecord.code == payload.location_code, WarehouseLocationRecord.active.is_(True))): raise HTTPException(422, "仓库与库位不匹配或已停用")
    if not db.scalar(select(MaterialRecord.id).where(MaterialRecord.code == payload.material_code, MaterialRecord.active.is_(True))): raise HTTPException(422, "物料编码不存在或已停用")


@router.post("/spare-stocks", status_code=201)
def create_stock(payload: StockIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); validate_stock_refs(db, payload)
    same = select(SpareStockRecord.id).where(SpareStockRecord.warehouse_code == payload.warehouse_code, SpareStockRecord.location_code == payload.location_code, SpareStockRecord.material_code == payload.material_code, SpareStockRecord.batch_no == payload.batch_no)
    if db.scalar(same): raise HTTPException(409, "相同仓库、库位、物料和批次的库存已存在")
    row = SpareStockRecord(**payload.model_dump(exclude={"version"})); db.add(row); db.commit(); db.refresh(row); return row


@router.put("/spare-stocks/{item_id}")
def update_stock(item_id: str, payload: StockIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); row = db.get(SpareStockRecord, item_id)
    if not row: raise HTTPException(404, "库存记录不存在")
    if row.version != payload.version: raise HTTPException(409, "记录已变化，请刷新后重试")
    validate_stock_refs(db, payload)
    for key, value in payload.model_dump(exclude={"version"}).items(): setattr(row, key, value)
    row.version += 1; db.commit(); db.refresh(row); return row


@router.delete("/spare-stocks/{item_id}", status_code=204)
def delete_stock(item_id: str, version: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); row = db.get(SpareStockRecord, item_id)
    if not row: raise HTTPException(404, "库存记录不存在")
    if row.version != version: raise HTTPException(409, "记录已变化，请刷新后重试")
    if row.quantity != 0: raise HTTPException(409, "库存数量不为零，不能删除；请通过收发或报废流程清零")
    db.delete(row); db.commit()


class MovementIn(BaseModel):
    movement_type: Literal["receipt", "issue", "return", "transfer", "scrap", "recycle"]
    warehouse_code: str = Field(min_length=1, max_length=64)
    from_location: str = Field(default="", max_length=64)
    to_location: str = Field(default="", max_length=64)
    material_code: str = Field(min_length=1, max_length=64)
    material_name: str = Field(default="", max_length=200)
    batch_no: str = Field(default="", max_length=64)
    quantity: Decimal = Field(gt=0)
    business_no: str = Field(default="", max_length=80)


def stock_at(db, warehouse, location, material, batch):
    return db.scalar(select(SpareStockRecord).where(SpareStockRecord.warehouse_code == warehouse, SpareStockRecord.location_code == location, SpareStockRecord.material_code == material, SpareStockRecord.batch_no == batch))


@router.get("/warehouse-movements")
def list_movements(keyword: str = "", movement_type: str = "", page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    clause = or_(WarehouseMovementRecord.movement_no.contains(keyword, autoescape=True), WarehouseMovementRecord.material_code.contains(keyword, autoescape=True), WarehouseMovementRecord.business_no.contains(keyword, autoescape=True))
    if movement_type: clause &= WarehouseMovementRecord.movement_type == movement_type
    return page(db, WarehouseMovementRecord, page_no, page_size, clause, WarehouseMovementRecord.happened_at.desc())


@router.post("/warehouse-movements", status_code=201)
def post_movement(payload: MovementIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user)
    adds = payload.movement_type in {"receipt", "return"}
    removes = payload.movement_type in {"issue", "scrap", "recycle"}
    if adds and not payload.to_location: raise HTTPException(422, "入库或退回必须选择目标库位")
    if removes and not payload.from_location: raise HTTPException(422, "领用、报废或回收必须选择来源库位")
    if payload.movement_type == "transfer" and (not payload.from_location or not payload.to_location or payload.from_location == payload.to_location): raise HTTPException(422, "移库必须选择不同的来源和目标库位")
    source = stock_at(db, payload.warehouse_code, payload.from_location, payload.material_code, payload.batch_no) if payload.from_location else None
    if (removes or payload.movement_type == "transfer") and (not source or source.quantity < payload.quantity): raise HTTPException(409, "来源库位可用库存不足")
    target = stock_at(db, payload.warehouse_code, payload.to_location, payload.material_code, payload.batch_no) if payload.to_location else None
    if adds or payload.movement_type == "transfer":
        if not target:
            if not db.scalar(select(WarehouseLocationRecord.id).where(WarehouseLocationRecord.warehouse_code == payload.warehouse_code, WarehouseLocationRecord.code == payload.to_location)): raise HTTPException(422, "目标库位不存在")
            target = SpareStockRecord(warehouse_code=payload.warehouse_code, location_code=payload.to_location, material_code=payload.material_code, material_name=payload.material_name, batch_no=payload.batch_no, quantity=0, received_date=datetime.now().astimezone().date())
            db.add(target)
        target.quantity += payload.quantity; target.version += 1
    if removes or payload.movement_type == "transfer":
        source.quantity -= payload.quantity; source.version += 1
        if payload.movement_type == "issue": source.last_issue_date = datetime.now().astimezone().date()
        if payload.movement_type in {"scrap", "recycle"} and source.quantity == 0: source.lifecycle_status = "scrapped" if payload.movement_type == "scrap" else "recycled"
    sequence = (db.scalar(select(func.count()).select_from(WarehouseMovementRecord)) or 0) + 1
    row = WarehouseMovementRecord(movement_no=f"WM-{sequence:06d}", **payload.model_dump(), operator=user.user_id)
    db.add(row); db.commit(); db.refresh(row); return row


class StocktakeIn(BaseModel):
    stock_id: str
    counted_quantity: Decimal = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)


@router.get("/stocktakes")
def list_stocktakes(keyword: str = "", page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    return page(db, StocktakeRecord, page_no, page_size, StocktakeRecord.material_code.contains(keyword, autoescape=True), StocktakeRecord.counted_at.desc())


@router.post("/stocktakes", status_code=201)
def post_stocktake(payload: StocktakeIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); stock = db.get(SpareStockRecord, payload.stock_id)
    if not stock: raise HTTPException(404, "库存记录不存在")
    book = stock.quantity; variance = payload.counted_quantity - book
    row = StocktakeRecord(stock_id=stock.id, warehouse_code=stock.warehouse_code, material_code=stock.material_code, book_quantity=book, counted_quantity=payload.counted_quantity, variance=variance, reason=payload.reason, counted_by=user.user_id)
    stock.quantity = payload.counted_quantity; stock.version += 1; db.add(row); db.commit(); db.refresh(row); return row


class SohIn(BaseModel):
    stock_id: str
    rust_score: int = Field(ge=0, le=100)
    moisture_score: int = Field(ge=0, le=100)
    dust_score: int = Field(ge=0, le=100)
    packaging_score: int = Field(ge=0, le=100)
    action: str = Field(default="", max_length=2000)


@router.get("/soh-inspections")
def list_soh(page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    return page(db, SohInspectionRecord, page_no, page_size, None, SohInspectionRecord.inspected_at.desc())


@router.post("/soh-inspections", status_code=201)
def create_soh(payload: SohIn, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_editor(user); stock = db.get(SpareStockRecord, payload.stock_id)
    if not stock: raise HTTPException(404, "库存记录不存在")
    avg = sum([payload.rust_score, payload.moisture_score, payload.dust_score, payload.packaging_score]) / 4
    conclusion = "good" if avg >= 85 else "attention" if avg >= 60 else "quarantine"
    row = SohInspectionRecord(**payload.model_dump(), conclusion=conclusion, inspected_by=user.user_id)
    stock.condition = conclusion; stock.version += 1; db.add(row); db.commit(); db.refresh(row); return row


@router.get("/warehouse/summary")
def warehouse_summary(db: Session = Depends(get_db)):
    stocks = db.scalars(select(SpareStockRecord)).all()
    low = [s for s in stocks if s.quantity <= s.reorder_point]
    excess = [s for s in stocks if s.max_stock > 0 and s.quantity > s.max_stock]
    care = [s for s in stocks if s.condition != "good"]
    dormant = [s for s in stocks if s.last_issue_date is None and s.quantity > 0]
    return {
        "warehouse_count": db.scalar(select(func.count()).select_from(WarehouseRecord)) or 0,
        "stock_skus": len(stocks), "stock_quantity": float(sum((s.quantity for s in stocks), Decimal(0))),
        "reorder_alerts": len(low), "excess_alerts": len(excess), "soh_alerts": len(care), "dormant_candidates": len(dormant),
        "alerts": [{"type": "补货", "material_code": s.material_code, "warehouse_code": s.warehouse_code, "message": f"现存{s.quantity}≤再订货点{s.reorder_point}"} for s in low]
                  + [{"type": "保养", "material_code": s.material_code, "warehouse_code": s.warehouse_code, "message": f"SOH状态：{s.condition}"} for s in care],
        "lifecycle": [{"material_code": s.material_code, "batch_no": s.batch_no, "status": s.lifecycle_status, "source_system": s.source_system, "received_date": s.received_date, "last_issue_date": s.last_issue_date, "expiry_date": s.expiry_date} for s in stocks],
    }
