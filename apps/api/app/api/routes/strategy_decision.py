import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import DateTime, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base, get_db
from app.core.security import CurrentUser, UserRole, require_roles
from app.domain.aviation_mro import (
    AviationMaterialProfileRecord,
    AviationSupplierCapabilityRecord,
)
from app.domain.material_policy import MaterialPolicy
from app.domain.persistence import MaterialRecord, SupplierRecord
from app.domain.spare_operations import SpareStockRecord
from app.services.strategy_decision import DecisionInput, analyze


class DecisionSnapshot(Base):
    __tablename__ = "spare_strategy_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


router = APIRouter(
    prefix="/strategy-decisions",
    tags=["strategy-decisions"],
    dependencies=[
        Depends(
            require_roles(
                UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER, UserRole.ANALYST
            )
        )
    ],
)


def material(db, code):
    m = db.scalar(
        select(MaterialRecord).where(MaterialRecord.code == code, MaterialRecord.active.is_(True))
    )
    policy = db.get(MaterialPolicy, code)
    if not m or not policy or json.loads(policy.payload).get("material_type") != "spare":
        raise HTTPException(422, "请选择有效备件物料")
    return m


def capability_options(db):
    rows = list(db.scalars(select(AviationSupplierCapabilityRecord)))
    suppliers = (
        {
            row.id: row
            for row in db.scalars(
                select(SupplierRecord).where(
                    SupplierRecord.id.in_([cap.supplier_id for cap in rows])
                )
            )
        }
        if rows
        else {}
    )
    return [
        {
            "supplier_id": cap.supplier_id,
            "supplier_code": suppliers[cap.supplier_id].code
            if cap.supplier_id in suppliers
            else "",
            "supplier_name": suppliers[cap.supplier_id].name
            if cap.supplier_id in suppliers
            else "",
            "capability_name": cap.capability_name,
            "supplier_type": cap.supplier_type,
            "oem_scope": cap.oem_scope,
            "part_scope": cap.part_scope,
            "offer_types": json.loads(cap.offer_types_json),
            "certificates": json.loads(cap.certificates_json),
            "aog_247": cap.aog_247,
            "response_hours": cap.response_hours,
            "relationship_status": cap.relationship_status,
            "public_reference": cap.public_reference,
        }
        for cap in rows
    ]


def analyze_material(db, code, payload):
    aviation = db.get(AviationMaterialProfileRecord, code)
    if aviation:
        options = capability_options(db)
        for candidate in payload.candidates:
            matches = [x for x in options if x["supplier_id"] == candidate.supplier_id]
            candidate.supplier_name = matches[0]["supplier_name"] if matches else ""
            candidate.supplier_aog_247 = any(x["aog_247"] for x in matches)
            candidate.supplier_response_hours = (
                min(x["response_hours"] for x in matches) if matches else None
            )
            candidate.shelf_life_required = aviation.shelf_life_days > 0
            if not matches:
                candidate.capability_status = "unmatched"
            elif any(
                x["relationship_status"] == "qualified"
                and (not x["offer_types"] or candidate.offer_type in x["offer_types"])
                for x in matches
            ):
                candidate.capability_status = "matched"
            else:
                candidate.capability_status = "unverified"
    return analyze(payload)


@router.get("/{code}/context")
def context(code: str, db: Session = Depends(get_db)):
    m = material(db, code)
    stocks = list(
        db.scalars(select(SpareStockRecord).where(SpareStockRecord.material_code == code))
    )
    aviation = db.get(AviationMaterialProfileRecord, code)
    aviation_view = None
    if aviation:
        aviation_view = {
            "part_number": aviation.part_number,
            "oem": aviation.oem,
            "ata_chapter": aviation.ata_chapter,
            "applicability": aviation.applicability,
            "allowed_conditions": json.loads(aviation.allowed_conditions_json),
            "certificates_required": json.loads(aviation.certificate_requirements_json),
            "trace_required": aviation.trace_required,
            "minimum_remaining_life": aviation.minimum_remaining_life,
            "minimum_remaining_life_percent": 30 if aviation.life_limited else 0,
            "shelf_life_days": aviation.shelf_life_days,
        }
    return {
        "material_code": code,
        "name": m.name,
        "classification": json.loads(db.get(MaterialPolicy, code).payload),
        "inventory": sum(
            float(s.quantity)
            for s in stocks
            if s.condition == "good" and s.lifecycle_status == "in_stock"
        ),
        "stock_rows": len(stocks),
        "aviation": aviation_view,
        "supplier_capabilities": capability_options(db) if aviation else [],
        "note": "仅提供良好在库数量参考，请扣除预留及不可调拨部分后确认；跨仓合计不代表可即时使用。",
    }


@router.post("/{code}/preview")
def preview(code: str, p: DecisionInput, db: Session = Depends(get_db)):
    material(db, code)
    return analyze_material(db, code, p)


@router.post("/{code}", status_code=201)
def save(
    code: str,
    p: DecisionInput,
    db: Session = Depends(get_db),
    u: CurrentUser = Depends(
        require_roles(UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER)
    ),
):
    material(db, code)
    result = analyze_material(db, code, p)
    row = DecisionSnapshot(
        material_code=code,
        payload=p.model_dump_json(),
        result=json.dumps(result, ensure_ascii=False, default=str),
        actor=u.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "created_at": row.created_at, "result": result}


@router.get("/{code}/history")
def history(
    code: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    material(db, code)
    q = select(DecisionSnapshot).where(DecisionSnapshot.material_code == code)
    rows = db.scalars(
        q.order_by(DecisionSnapshot.created_at.desc(), DecisionSnapshot.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            {
                "id": r.id,
                "created_at": r.created_at,
                "actor": r.actor,
                "input": json.loads(r.payload),
                "result": json.loads(r.result),
            }
            for r in rows
        ],
        "total": db.scalar(
            select(func.count())
            .select_from(DecisionSnapshot)
            .where(DecisionSnapshot.material_code == code)
        ),
    }


@router.get("/{code}/example")
def example(code: str, db: Session = Depends(get_db)):
    selected_material = material(db, code)
    today = datetime.now(UTC).date()
    baseline = float(selected_material.standard_price or 0) or 100
    price_scale = baseline / 100
    result = {
        "quantity": 10,
        "required_date": str(today + timedelta(days=7)),
        "budget": baseline * 15,
        "baseline_price": baseline,
        "premium_limit": 20,
        "risk_limit": 10,
        "downtime_per_day": 500,
        "annual_issues": 1,
        "critical": True,
        "reserve": 2,
        "available": 2,
        "inventory_confirmed": True,
        "owner": "演示采购经理",
        "evidence": "【模拟】需求及库存仅演示，CNY同口径费用；不代表真实采购依据",
        "simulated": True,
        "demand_type": "planned",
        "required_within_hours": None,
        "candidates": [
            {
                "name": name,
                "source": source,
                "supply_mode": mode,
                "unit_price": round(price * price_scale, 2),
                "fees": 50,
                "holding_cost": 20,
                "validation_cost": validation,
                "arrival": str(today + timedelta(days=days)),
                "validated": valid,
                "reliability": reliability,
                "available_quantity": 20 if days <= 5 else 8,
                "minimum_order_quantity": 1,
                "package_quantity": 1,
                "repair_tat_days": None,
                "repair_success_rate": None,
                "ber_probability": 8 if name == "原厂加急" else None,
                "shelf_life_remaining_days": 540,
                "evidence": "【模拟】报价、交期与履约数据",
            }
            for name, source, mode, price, days, valid, reliability, validation in [
                ("原厂常规", "oem", "standard", 100, 12, True, 98, 0),
                ("原厂加急", "oem", "framework", 115, 5, True, 98, 0),
                ("国产待验证", "domestic", "standard", 70, 4, False, 92, 100),
                ("寄售保障", "alternative", "consignment", 90, 3, True, 96, 0),
            ]
        ],
    }
    if db.get(AviationMaterialProfileRecord, code):
        result["demand_type"] = "aog"
        result["required_within_hours"] = 6
        options = capability_options(db)
        qualified = [x for x in options if x["relationship_status"] == "qualified"]
        references = [x for x in options if x["public_reference"]]
        choices = [
            references[0] if references else None,
            qualified[0] if qualified else None,
            references[1] if len(references) > 1 else (references[0] if references else None),
            qualified[0] if qualified else None,
        ]
        for candidate, supplier in zip(result["candidates"], choices, strict=True):
            if supplier:
                candidate["supplier_id"] = supplier["supplier_id"]
                candidate["supplier_name"] = supplier["supplier_name"]
    return result
