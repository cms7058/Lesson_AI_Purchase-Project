"""Add-only seller-led MRO forecasting teaching data."""

# The compact dict(...) profile declarations are intentionally used as teaching fixtures.
# ruff: noqa: C408

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.domain.mro_intelligence import (
    MroDemandEventRecord,
    MroLeadTimeRecord,
    MroMaterialProfileRecord,
    MroSupplyPositionRecord,
)
from app.domain.spare_operations import WarehouseLocationRecord, WarehouseRecord

PROFILES = {
    "DEMO-AERO-001": dict(
        demand_characteristic="stable",
        aircraft_impact=2,
        supply_risk=2,
        lead_time_risk=2,
        value_level=1,
        substitutability=5,
        compliance_risk=3,
        repairability=1,
        evidence="教学画像：高频标准紧固件，SAP/WMS稳定消耗",
    ),
    "DEMO-AERO-002": dict(
        demand_characteristic="intermittent",
        aircraft_impact=4,
        supply_risk=3,
        lead_time_risk=3,
        value_level=3,
        substitutability=2,
        compliance_risk=4,
        repairability=2,
        non_routine=True,
        evidence="教学画像：间歇需求、低可替代连接器",
    ),
    "DEMO-AERO-003": dict(
        demand_characteristic="planned",
        aircraft_impact=5,
        supply_risk=4,
        lead_time_risk=4,
        value_level=4,
        substitutability=2,
        compliance_risk=5,
        repairability=4,
        repairable=True,
        high_value=True,
        evidence="教学画像：关键可修理传感器",
    ),
    "DEMO-AERO-004": dict(
        demand_characteristic="planned",
        aircraft_impact=5,
        supply_risk=5,
        lead_time_risk=5,
        value_level=5,
        substitutability=1,
        compliance_risk=5,
        repairability=5,
        single_source=True,
        long_lead=True,
        high_value=True,
        repairable=True,
        non_routine=True,
        evidence="教学画像：单一来源+长交期+高价值，以AMOS维修事件驱动",
    ),
    "DEMO-AERO-005": dict(
        demand_characteristic="stable",
        aircraft_impact=3,
        supply_risk=2,
        lead_time_risk=2,
        value_level=2,
        substitutability=4,
        compliance_risk=4,
        repairability=1,
        evidence="教学画像：批次与寿命受控密封件",
    ),
    "DEMO-AERO-008": dict(
        demand_characteristic="lumpy",
        aircraft_impact=5,
        supply_risk=4,
        lead_time_risk=4,
        value_level=4,
        substitutability=2,
        compliance_risk=5,
        repairability=4,
        repairable=True,
        high_value=True,
        non_routine=True,
        evidence="教学画像：刹车消耗件，重检事件与非例行需求并存",
    ),
}


def seed(db):
    from app.seed_aviation_demo import seed as seed_aviation

    seed_aviation(db)
    today = datetime.now(UTC).date()
    counts = {"profiles": 0, "demand_events": 0, "supply_positions": 0, "lead_samples": 0, "warehouses": 0, "locations": 0}
    warehouses = [
        ("WMS-MAIN", "【演示】自有中央航材库", "自有库存，由WMS管理", "演示仓管员"),
        ("CONS-HKG", "【演示】香港寄售库", "供应商寄售库存", "寄售协调员"),
        ("VMI-XMN", "【演示】厦门VMI库", "供应商管理库存", "VMI协调员"),
        ("REPAIR-POOL", "【演示】修理回转库", "可修理件周转池", "修理计划员"),
    ]
    for code, name, address, manager in warehouses:
        warehouse = db.scalar(select(WarehouseRecord).where(WarehouseRecord.code == code))
        if not warehouse:
            warehouse = WarehouseRecord(code=code, name=name, factory_code="MRO", address=address, manager=manager)
            db.add(warehouse)
            counts["warehouses"] += 1
        location = db.scalar(select(WarehouseLocationRecord).where(WarehouseLocationRecord.warehouse_code == code, WarehouseLocationRecord.code == "MRO-01"))
        if not location:
            db.add(WarehouseLocationRecord(warehouse_code=code, code="MRO-01", name=f"{name}默认拣货位", zone_type="critical", near_maintenance=code in {"WMS-MAIN", "REPAIR-POOL"}, temperature_controlled=True))
            counts["locations"] += 1
    for code, values in PROFILES.items():
        row = db.get(MroMaterialProfileRecord, code)
        if not row:
            row = MroMaterialProfileRecord(material_code=code, **values)
            db.add(row)
            counts["profiles"] += 1

        for month in range(1, 13):
            event_date = today - timedelta(days=month * 30)
            if code in {"DEMO-AERO-002", "DEMO-AERO-008"} and month % 3:
                continue
            base = {
                "DEMO-AERO-001": 34,
                "DEMO-AERO-002": 2,
                "DEMO-AERO-003": 1,
                "DEMO-AERO-004": 1,
                "DEMO-AERO-005": 10,
                "DEMO-AERO-008": 3,
            }[code]
            quantity = base + ((month * 7) % 5 - 2)
            ref = f"MRO-DEMO-HIST-{code}-{month:02d}"
            exists = db.scalar(
                select(MroDemandEventRecord.id).where(MroDemandEventRecord.source_ref == ref)
            )
            if not exists:
                db.add(
                    MroDemandEventRecord(
                        material_code=code,
                        event_date=event_date,
                        quantity=max(1, quantity),
                        demand_type="consumption",
                        probability=1,
                        confirmed=True,
                        source_system="WMS",
                        source_ref=ref,
                        evidence="【演示】历史领用/消耗记录",
                    )
                )
                counts["demand_events"] += 1

        future_specs = [
            (45, 1, "planned", 1.0),
            (105, 1 if code != "DEMO-AERO-001" else 28, "planned", 1.0),
            (150, 1, "non_routine", 0.35),
        ]
        for index, (days, quantity, demand_type, probability) in enumerate(future_specs):
            ref = f"MRO-DEMO-AMOS-{code}-{index}"
            exists = db.scalar(
                select(MroDemandEventRecord.id).where(MroDemandEventRecord.source_ref == ref)
            )
            if not exists:
                db.add(
                    MroDemandEventRecord(
                        material_code=code,
                        event_date=today + timedelta(days=days),
                        quantity=quantity,
                        demand_type=demand_type,
                        probability=probability,
                        confirmed=demand_type == "planned",
                        source_system="AMOS",
                        source_ref=ref,
                        evidence="【演示】AMOS维修包/非例行概率事件",
                    )
                )
                counts["demand_events"] += 1

        positions = [
            ("owned", "WMS-MAIN", 2 if code != "DEMO-AERO-001" else 25, "WMS"),
            (
                "consignment",
                "CONS-HKG",
                1 if code in {"DEMO-AERO-003", "DEMO-AERO-004"} else 0,
                "CONSIGNMENT",
            ),
            ("vmi", "VMI-XMN", 2 if code in {"DEMO-AERO-001", "DEMO-AERO-005"} else 0, "VMI"),
            (
                "repair_return",
                "REPAIR-POOL",
                1 if code in {"DEMO-AERO-003", "DEMO-AERO-008"} else 0,
                "AMOS",
            ),
        ]
        for position_type, warehouse, quantity, source in positions:
            if quantity <= 0:
                continue
            ref = f"MRO-DEMO-POS-{code}-{position_type}"
            exists = db.scalar(
                select(MroSupplyPositionRecord.id).where(MroSupplyPositionRecord.source_ref == ref)
            )
            if not exists:
                db.add(
                    MroSupplyPositionRecord(
                        material_code=code,
                        position_type=position_type,
                        warehouse_code=warehouse,
                        quantity=quantity,
                        reserved_quantity=0,
                        quarantined_quantity=0,
                        available_date=today,
                        confirmed=True,
                        source_system=source,
                        source_ref=ref,
                    )
                )
                counts["supply_positions"] += 1

        center = {
            "DEMO-AERO-001": 32,
            "DEMO-AERO-002": 70,
            "DEMO-AERO-003": 115,
            "DEMO-AERO-004": 185,
            "DEMO-AERO-005": 48,
            "DEMO-AERO-008": 92,
        }[code]
        for index in range(12):
            ref = f"MRO-DEMO-LEAD-{code}-{index}"
            exists = db.scalar(
                select(MroLeadTimeRecord.id).where(MroLeadTimeRecord.source_ref == ref)
            )
            if not exists:
                spread = ((index * 11) % 17) - 8
                if index == 11 and code in {"DEMO-AERO-003", "DEMO-AERO-004"}:
                    spread += 35
                db.add(
                    MroLeadTimeRecord(
                        material_code=code,
                        supplier_name="【演示】航材供应商",
                        transaction_type="purchase",
                        days=max(5, center + spread),
                        happened_date=today - timedelta(days=(index + 1) * 32),
                        source_system="SAP",
                        source_ref=ref,
                    )
                )
                counts["lead_samples"] += 1
    db.commit()
    return counts
