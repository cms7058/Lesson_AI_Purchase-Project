"""Add-only aviation MRO teaching data. Public names are references, not asserted relationships."""

import json
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.database import SessionLocal
from app.domain.aviation_mro import AviationMaterialProfileRecord, AviationSupplierCapabilityRecord
from app.domain.material_policy import MaterialPolicy
from app.domain.persistence import (
    MaterialCategoryAssignmentRecord,
    MaterialCategoryRecord,
    MaterialRecord,
    SupplierRecord,
)
from app.domain.spare_operations import SpareProcurementStrategyRecord, SpareStockRecord


def uid(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, "ai-assist-aviation-mro-demo-v1/" + key))


SUPPLIERS = [
    (
        "DEMO-AERO-S01",
        "【公开资料参考】Satair",
        "authorized_distributor",
        "Airbus标准件、消耗件与寄售库存",
        True,
        24,
    ),
    (
        "DEMO-AERO-S02",
        "【公开资料参考】Boeing Distribution Services",
        "authorized_distributor",
        "Boeing备件、紧固件与消耗件",
        True,
        24,
    ),
    (
        "DEMO-AERO-S03",
        "【公开资料参考】Global Aviation Co",
        "distributor",
        "航材分销、PMA、寄售与全球寻源",
        True,
        24,
    ),
    (
        "DEMO-AERO-S04",
        "【公开资料参考】Proponent",
        "distributor",
        "航空零部件、材料与长尾供应",
        True,
        24,
    ),
    (
        "DEMO-AERO-S05",
        "【公开资料参考】Liebherr-Aerospace",
        "oem",
        "起落架系统及技术支持",
        False,
        48,
    ),
    (
        "DEMO-AERO-S06",
        "【公开资料参考】Woodward",
        "oem",
        "燃油控制、执行机构与空气管理系统",
        False,
        48,
    ),
    (
        "DEMO-AERO-S07",
        "【公开资料参考】Safran Aircraft Engines",
        "oem",
        "LEAP发动机相关部件与技术支持",
        False,
        48,
    ),
    (
        "DEMO-AERO-S08",
        "【演示】全天候AOG航材服务商",
        "trader",
        "Exchange、Loan、USM与24/7紧急寻源",
        True,
        2,
    ),
    (
        "DEMO-AERO-S09",
        "【演示】航空工具与检测设备供应商",
        "distributor",
        "维修工装、NDT、校准与地面保障设备",
        False,
        8,
    ),
]

MATERIALS = [
    (
        "DEMO-AERO-001",
        "航空标准紧固件",
        "AERO-DEMO-PN-001",
        "Airframe OEM",
        "20",
        "A320/B737教学构型",
        "C",
        "E",
        "F",
        36,
        180,
        False,
        ["NEW"],
        ["CoC"],
    ),
    (
        "DEMO-AERO-002",
        "电气连接器组件",
        "AERO-DEMO-PN-002",
        "Connector OEM",
        "24",
        "窄体机航电线路教学构型",
        "B",
        "V",
        "S",
        1200,
        45,
        True,
        ["NEW", "USM"],
        ["8130-3", "EASA Form 1"],
    ),
    (
        "DEMO-AERO-003",
        "压力传感器",
        "AERO-DEMO-PN-003",
        "Sensor OEM",
        "31",
        "飞行仪表教学构型",
        "A",
        "V",
        "S",
        18500,
        120,
        True,
        ["NEW", "OH", "USM"],
        ["8130-3", "EASA Form 1"],
    ),
    (
        "DEMO-AERO-004",
        "液压控制阀",
        "AERO-DEMO-PN-004",
        "Hydraulic OEM",
        "29",
        "液压系统教学构型",
        "A",
        "V",
        "S",
        68000,
        180,
        True,
        ["NEW", "OH", "SV", "USM"],
        ["8130-3", "EASA Form 1", "维修履历"],
    ),
    (
        "DEMO-AERO-005",
        "航空密封件套件",
        "AERO-DEMO-PN-005",
        "Seal OEM",
        "32",
        "起落架维修教学构型",
        "B",
        "E",
        "F",
        950,
        60,
        False,
        ["NEW"],
        ["CoC", "批次追溯"],
    ),
    (
        "DEMO-AERO-006",
        "客舱照明组件",
        "AERO-DEMO-PN-006",
        "Cabin OEM",
        "33",
        "客舱改装教学构型",
        "B",
        "E",
        "S",
        7200,
        75,
        True,
        ["NEW", "OH", "USM"],
        ["8130-3"],
    ),
    (
        "DEMO-AERO-007",
        "线束维修组件",
        "AERO-DEMO-PN-007",
        "Harness OEM",
        "92",
        "结构与线束修理教学构型",
        "B",
        "V",
        "S",
        4800,
        30,
        False,
        ["NEW"],
        ["CoC", "制造批次"],
    ),
    (
        "DEMO-AERO-008",
        "机轮刹车消耗件",
        "AERO-DEMO-PN-008",
        "Brake OEM",
        "32",
        "机轮刹车教学构型",
        "A",
        "V",
        "F",
        12800,
        90,
        True,
        ["NEW", "OH"],
        ["8130-3", "EASA Form 1"],
    ),
    (
        "DEMO-AERO-009",
        "发动机孔探检测设备",
        "AERO-DEMO-TOOL-009",
        "Tool OEM",
        "72",
        "LEAP/GE90教学用途",
        "A",
        "E",
        "S",
        260000,
        60,
        True,
        ["NEW"],
        ["校准证书", "设备合格证"],
    ),
    (
        "DEMO-AERO-010",
        "无损检测渗透耗材",
        "AERO-DEMO-NDT-010",
        "NDT OEM",
        "51",
        "NDT工艺教学用途",
        "C",
        "E",
        "F",
        680,
        20,
        False,
        ["NEW"],
        ["CoC", "SDS", "批次追溯"],
    ),
    (
        "DEMO-AERO-011",
        "扭矩校准工具",
        "AERO-DEMO-TOOL-011",
        "Tool OEM",
        "20",
        "通用维修工具",
        "B",
        "E",
        "S",
        15000,
        35,
        True,
        ["NEW"],
        ["校准证书"],
    ),
    (
        "DEMO-AERO-012",
        "地面保障设备配件",
        "AERO-DEMO-GSE-012",
        "GSE OEM",
        "12",
        "地面保障设备",
        "C",
        "D",
        "N",
        3200,
        25,
        False,
        ["NEW", "REMAN"],
        ["CoC"],
    ),
]


def seed(db):
    counts = {}

    def put(model, key, **values):
        row = db.get(model, uid(key))
        if row:
            return row
        row = model(id=uid(key), **values)
        db.add(row)
        db.flush()
        counts[model.__tablename__] = counts.get(model.__tablename__, 0) + 1
        return row

    root = put(
        MaterialCategoryRecord,
        "cat-root",
        code="DAERO",
        name="【演示】航空MRO",
        level=1,
        parent_id=None,
        path_name="【演示】航空MRO",
        created_by="aviation-demo",
    )
    group = put(
        MaterialCategoryRecord,
        "cat-group",
        code="DAERO-01",
        name="【演示】航材与维修保障",
        level=2,
        parent_id=root.id,
        path_name=f"{root.path_name} / 航材与维修保障",
        created_by="aviation-demo",
    )
    leaf = put(
        MaterialCategoryRecord,
        "cat-leaf",
        code="DAERO-01-01",
        name="【演示】航空备件与工具",
        level=3,
        parent_id=group.id,
        path_name=f"{group.path_name} / 航空备件与工具",
        created_by="aviation-demo",
    )

    suppliers = []
    for code, name, supplier_type, scope, aog, hours in SUPPLIERS:
        row = db.scalar(select(SupplierRecord).where(SupplierRecord.code == code))
        if not row:
            row = put(
                SupplierRecord,
                code,
                code=code,
                name=name,
                category="航空MRO",
                status="candidate" if "公开资料" in name else "qualified",
                risk_level="medium" if "公开资料" in name else "low",
                address="【演示】非真实交易地址",
                created_by="aviation-demo",
            )
        suppliers.append(row)
        if not db.get(AviationSupplierCapabilityRecord, uid("cap-" + code)):
            db.add(
                AviationSupplierCapabilityRecord(
                    id=uid("cap-" + code),
                    supplier_id=row.id,
                    capability_name=scope,
                    supplier_type=supplier_type,
                    oem_scope=scope,
                    part_scope="航空备件、维修保障与相关服务；实际适用范围须逐项核验",
                    offer_types_json=json.dumps(
                        ["purchase", "exchange", "loan"] if aog else ["purchase", "repair"],
                        ensure_ascii=False,
                    ),
                    certificates_json=json.dumps(
                        ["供应商资质待核验", "PN适用性需逐项核验"], ensure_ascii=False
                    ),
                    aog_247=aog,
                    response_hours=hours,
                    public_reference="公开资料" in name,
                    relationship_status="not_verified" if "公开资料" in name else "qualified",
                    evidence="【演示】来自用户提供的公开资料场景；不证明真实准入、库存或商务关系",
                )
            )

    materials = []
    for (
        code,
        name,
        pn,
        oem,
        ata,
        applicability,
        abc,
        ved,
        fsn,
        price,
        lead,
        serial,
        conditions,
        certs,
    ) in MATERIALS:
        row = db.scalar(select(MaterialRecord).where(MaterialRecord.code == code))
        if not row:
            row = put(
                MaterialRecord,
                code,
                code=code,
                name="【演示】" + name,
                specification=f"{pn} / 虚构PN，仅供教学",
                category=leaf.path_name,
                unit="件",
                standard_price=Decimal(price),
                safety_stock=Decimal(1 if ved == "V" else 0),
                lead_time_days=lead,
                created_by="aviation-demo",
            )
            db.add(
                MaterialPolicy(
                    material_code=code,
                    payload=json.dumps(
                        {
                            "material_type": "spare",
                            "abc": abc,
                            "ved": ved,
                            "fsn": fsn,
                            "reason": "【演示】按航空MRO年度价值、适航关键性和领用频次分类",
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            db.add(
                MaterialCategoryAssignmentRecord(
                    id=uid("assign-" + code), material_id=row.id, category_id=leaf.id
                )
            )
        materials.append(row)
        if not db.get(AviationMaterialProfileRecord, code):
            db.add(
                AviationMaterialProfileRecord(
                    material_code=code,
                    part_number=pn,
                    oem=oem,
                    ata_chapter=ata,
                    applicability=applicability,
                    serial_controlled=serial,
                    batch_controlled=not serial,
                    allowed_conditions_json=json.dumps(conditions),
                    certificate_requirements_json=json.dumps(certs, ensure_ascii=False),
                    trace_required=True,
                    shelf_life_days=730 if "耗材" in name or "密封" in name else 0,
                    life_limited=serial,
                    minimum_remaining_life="≥30%或经工程批准" if serial else "",
                    default_offer_type="exchange"
                    if code in {"DEMO-AERO-003", "DEMO-AERO-004"}
                    else "purchase",
                    note="【演示】所有PN、构型和价格均为虚构数据",
                )
            )

    for i, material in enumerate(materials[:4]):
        if not db.get(SpareStockRecord, uid("stock-" + material.code)):
            db.add(
                SpareStockRecord(
                    id=uid("stock-" + material.code),
                    warehouse_code="DEMO-AERO-WH",
                    location_code=f"A-{i + 1:02}",
                    material_code=material.code,
                    material_name=material.name,
                    batch_no=f"AERO-DEMO-B{i + 1:02}",
                    quantity=Decimal([50, 3, 0, 1][i]),
                    safety_stock=Decimal([20, 2, 1, 1][i]),
                    min_stock=Decimal(1),
                    reorder_point=Decimal(2),
                    max_stock=Decimal(60),
                    planned_reserve=Decimal(1),
                    condition="good",
                    source_system="DEMO-AERO-WMS",
                )
            )
        if not db.get(SpareProcurementStrategyRecord, uid("strategy-" + material.code)):
            db.add(
                SpareProcurementStrategyRecord(
                    id=uid("strategy-" + material.code),
                    name=f"【演示】{material.name}航空MRO采购策略",
                    material_code=material.code,
                    source_mode="oem" if i < 2 else "alternative",
                    supplier_model="consignment" if i == 0 else "framework",
                    urgency="shutdown" if i == 2 else "planned",
                    price_baseline=material.standard_price,
                    premium_limit=Decimal(35 if i == 2 else 15),
                    lead_time_days=material.lead_time_days,
                    decision_status="reviewing",
                    rationale="【演示】必须先通过适航证书、追溯、适用性与剩余寿命硬门槛，再比较TOC",
                    fallback_plan="【演示】主供失效时评估Exchange、Loan、USM或共享库存",
                    created_by="aviation-demo",
                )
            )
    db.commit()
    return counts | {"suppliers": len(suppliers), "materials": len(materials)}


if __name__ == "__main__":
    with SessionLocal() as session:
        print(json.dumps(seed(session), ensure_ascii=False, indent=2))
