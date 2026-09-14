"""Idempotent, clearly labelled demonstration data for spare strategy and warehousing."""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.domain.persistence import MaterialRecord
from app.domain.spare_operations import (
    SohInspectionRecord, SpareProcurementStrategyRecord, SpareStockRecord,
    StocktakeRecord, WarehouseLocationRecord, WarehouseMovementRecord, WarehouseRecord,
)
from app.api.routes.strategy_decision import DecisionSnapshot
from app.services.strategy_decision import DecisionInput, analyze


def uid(name):
    return str(uuid5(NAMESPACE_URL, "pebs-spare-warehouse-demo-v1:" + name))


def decision_scenarios(materials):
    today = date.today()
    common = {
        "inventory_confirmed": True,
        "owner": "【演示】备件采购经理",
        "simulated": True,
    }
    evidence = "【模拟】报价、交期、履约和技术状态仅用于联合策略功能演示"
    return [
        {
            **common, "material_code": materials[0].code, "quantity": 10,
            "required_date": today + timedelta(days=7), "budget": 1500,
            "baseline_price": 100, "premium_limit": 20, "risk_limit": 10,
            "downtime_per_day": 500, "annual_issues": 1, "critical": True,
            "reserve": 2, "available": 2,
            "evidence": "【模拟】停机维修需求；库存口径已扣除预留；价格统一为CNY含税",
            "candidates": [
                {"name": "【演示】原厂常规", "source": "oem", "supply_mode": "standard", "unit_price": 100, "fees": 50, "holding_cost": 20, "validation_cost": 0, "arrival": today + timedelta(days=12), "validated": True, "reliability": 98, "evidence": evidence},
                {"name": "【演示】原厂加急", "source": "oem", "supply_mode": "framework", "unit_price": 115, "fees": 50, "holding_cost": 20, "validation_cost": 0, "arrival": today + timedelta(days=5), "validated": True, "reliability": 98, "evidence": evidence},
                {"name": "【演示】国产待验证", "source": "domestic", "supply_mode": "standard", "unit_price": 70, "fees": 50, "holding_cost": 20, "validation_cost": 100, "arrival": today + timedelta(days=4), "validated": False, "reliability": 92, "evidence": evidence},
            ],
        },
        {
            **common, "material_code": materials[1].code, "quantity": 6,
            "required_date": today + timedelta(days=20), "budget": 3500,
            "baseline_price": 420, "premium_limit": 10, "risk_limit": 8,
            "downtime_per_day": 800, "annual_issues": 8, "critical": True,
            "reserve": 2, "available": 1,
            "evidence": "【模拟】年度领用台账与国产化验证报告；价格统一为CNY含税",
            "candidates": [
                {"name": "【演示】进口原厂", "source": "oem", "supply_mode": "standard", "unit_price": 430, "fees": 180, "holding_cost": 80, "validation_cost": 0, "arrival": today + timedelta(days=18), "validated": True, "reliability": 98, "evidence": evidence},
                {"name": "【演示】国产VMI", "source": "domestic", "supply_mode": "vmi", "unit_price": 330, "fees": 120, "holding_cost": 60, "validation_cost": 0, "arrival": today + timedelta(days=9), "validated": True, "reliability": 95, "agreement_reviewed": True, "evidence": evidence + "；【模拟】VMI所有权及结算条款已评审"},
            ],
        },
        {
            **common, "material_code": materials[2].code, "quantity": 4,
            "required_date": today + timedelta(days=30), "budget": 8000,
            "baseline_price": 1250, "premium_limit": 15, "risk_limit": 12,
            "downtime_per_day": 1200, "annual_issues": 3, "critical": False,
            "reserve": 2, "available": 35,
            "evidence": "【模拟】WMS可用库存35件，已扣除冻结与预留；无需新增采购",
            "candidates": [
                {"name": "【演示】框架补货", "source": "alternative", "supply_mode": "framework", "unit_price": 1250, "fees": 100, "holding_cost": 50, "validation_cost": 0, "arrival": today + timedelta(days=15), "validated": True, "reliability": 94, "evidence": evidence},
            ],
        },
        {
            **common, "material_code": materials[3].code, "quantity": 2,
            "required_date": today + timedelta(days=25), "budget": 500,
            "baseline_price": 95, "premium_limit": 15, "risk_limit": 12,
            "downtime_per_day": 100, "annual_issues": 1, "critical": False,
            "reserve": 1, "available": 0,
            "evidence": "【模拟】低值低频领用记录、共享库存承诺与平台报价；CNY含税",
            "candidates": [
                {"name": "【演示】行业共享库存", "source": "shared_stock", "supply_mode": "consignment", "unit_price": 80, "fees": 10, "holding_cost": 5, "validation_cost": 0, "arrival": today + timedelta(days=6), "validated": True, "reliability": 96, "agreement_reviewed": True, "evidence": evidence + "；【模拟】共享库存协议已评审"},
                {"name": "【演示】平台零散采购", "source": "platform", "supply_mode": "standard", "unit_price": 95, "fees": 30, "holding_cost": 5, "validation_cost": 0, "arrival": today + timedelta(days=10), "validated": True, "reliability": 93, "evidence": evidence},
            ],
        },
    ]


def run():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        materials = list(db.scalars(select(MaterialRecord).where(MaterialRecord.created_by == "spare-demo").order_by(MaterialRecord.code).limit(4)))
        if not materials:
            return 0
        warehouses = [
            WarehouseRecord(id=uid("wh-main"), code="DEMO-WH-MRO", name="【演示】中央备件库", factory_code="DEMO-SP-F01", address="维修中心东侧", manager="演示仓管员", maintenance_distance_m=Decimal("80")),
            WarehouseRecord(id=uid("wh-line"), code="DEMO-WH-LINE", name="【演示】产线卫星库", factory_code="DEMO-SP-F01", address="装配线维修区", manager="演示维修员", maintenance_distance_m=Decimal("12")),
        ]
        for row in warehouses:
            if not db.get(WarehouseRecord, row.id): db.add(row)
        locations = [
            ("fast", "DEMO-WH-MRO", "F-01", "【演示】高频近维修区", "fast", True, False),
            ("heavy", "DEMO-WH-MRO", "H-01", "【演示】重型备件区", "heavy", False, True),
            ("critical", "DEMO-WH-MRO", "V-01", "【演示】关键事故件区", "critical", False, False),
            ("line", "DEMO-WH-LINE", "L-01", "【演示】产线快速库位", "fast", True, False),
        ]
        for key, wh, code, name, zone, near, heavy in locations:
            if not db.get(WarehouseLocationRecord, uid("loc-" + key)):
                db.add(WarehouseLocationRecord(id=uid("loc-" + key), warehouse_code=wh, code=code, name=name, zone_type=zone, near_maintenance=near, heavy_duty=heavy, temperature_controlled=zone == "critical", humidity_limit=Decimal("65")))
        db.flush()
        configs = [(materials[0], "F-01", 4, 2, 3, 5, 20, "good"), (materials[1], "V-01", 1, 1, 2, 3, 8, "attention"), (materials[2], "H-01", 35, 2, 5, 8, 20, "good"), (materials[3], "L-01", 6, 2, 3, 5, 12, "good")]
        for i, (m, loc, qty, safety, minimum, reorder, maximum, condition) in enumerate(configs):
            wh = "DEMO-WH-LINE" if loc == "L-01" else "DEMO-WH-MRO"
            row = SpareStockRecord(id=uid("stock-" + m.code), warehouse_code=wh, location_code=loc, material_code=m.code, material_name=m.name, batch_no=f"DEMO-B{i+1:02}", quantity=Decimal(qty), safety_stock=Decimal(safety), min_stock=Decimal(minimum), reorder_point=Decimal(reorder), max_stock=Decimal(maximum), planned_reserve=Decimal(2 if i < 2 else 0), condition=condition, received_date=date.today() - timedelta(days=90 + i * 40), source_system="DEMO-WMS")
            if not db.get(SpareStockRecord, row.id): db.add(row)
        strategies = [
            ("oem", materials[0], "【演示】关键件OEM双供", "oem", "framework", "planned", 680, 8),
            ("domestic", materials[1], "【演示】进口密封件国产替代", "domestic", "vmi", "planned", 420, 10),
            ("urgent", materials[2], "【演示】停机抢修应急采购", "alternative", "standard", "shutdown", 1250, 25),
            ("longtail", materials[3], "【演示】长尾件共享库存", "shared_stock", "consignment", "planned", 95, 5),
        ]
        for key, m, name, mode, model, urgency, price, premium in strategies:
            if not db.get(SpareProcurementStrategyRecord, uid("strategy-" + key)):
                db.add(SpareProcurementStrategyRecord(id=uid("strategy-" + key), name=name, material_code=m.code, source_mode=mode, supplier_model=model, urgency=urgency, price_baseline=Decimal(price), premium_limit=Decimal(premium), lead_time_days=7, decision_status="approved", rationale="【演示】综合技术等效性、停机风险、历史价格和TOC评审", fallback_plan="【演示】主供失效时切换框架备选供应商", created_by="spare-operations-demo"))
        first = configs[0][0]
        if not db.get(WarehouseMovementRecord, uid("movement")):
            db.add(WarehouseMovementRecord(id=uid("movement"), movement_no="DEMO-WM-000001", movement_type="receipt", warehouse_code="DEMO-WH-MRO", to_location="F-01", material_code=first.code, material_name=first.name, batch_no="DEMO-B01", quantity=Decimal(4), business_no="DEMO-GR-001", operator="演示仓管员"))
        second_stock = uid("stock-" + materials[1].code)
        if not db.get(StocktakeRecord, uid("stocktake")):
            db.add(StocktakeRecord(id=uid("stocktake"), stock_id=second_stock, warehouse_code="DEMO-WH-MRO", material_code=materials[1].code, book_quantity=Decimal(2), counted_quantity=Decimal(1), variance=Decimal(-1), reason="【演示】月度盘点发现包装破损隔离", counted_by="演示仓管员"))
        if not db.get(SohInspectionRecord, uid("soh")):
            db.add(SohInspectionRecord(id=uid("soh"), stock_id=second_stock, rust_score=72, moisture_score=58, dust_score=68, packaging_score=55, conclusion="attention", action="【演示】更换包装并转入防潮区", inspected_by="演示设备工程师"))
        for index, raw in enumerate(decision_scenarios(materials)):
            snapshot_id = uid(f"strategy-decision-{index + 1}")
            if db.get(DecisionSnapshot, snapshot_id):
                continue
            material_code = raw.pop("material_code")
            payload = DecisionInput.model_validate(raw)
            result = analyze(payload)
            db.add(DecisionSnapshot(
                id=snapshot_id,
                material_code=material_code,
                payload=payload.model_dump_json(),
                result=json.dumps(result, ensure_ascii=False, default=str),
                actor="spare-strategy-demo",
                created_at=datetime.now() - timedelta(days=4 - index),
            ))
        db.commit()
        return len(materials)


if __name__ == "__main__":
    print(f"seeded spare operation materials: {run()}")
