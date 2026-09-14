from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
MANAGER = {"X-User-Id": "mro-manager", "X-User-Role": "procurement_manager"}
ANALYST = {"X-User-Id": "mro-analyst", "X-User-Role": "analyst"}


def create_fixture() -> tuple[dict, dict, dict]:
    tag = uuid4().hex[:8]
    factory = client.post(
        "/api/v1/factories",
        headers=MANAGER,
        json={"code": f"MRO-F-{tag}", "name": f"MRO测试工厂{tag}"},
    )
    assert factory.status_code == 201, factory.text
    material = client.post(
        "/api/v1/materials",
        headers=MANAGER,
        json={
            "code": f"MRO-SP-{tag}",
            "name": "主轴轴承",
            "unit": "套",
            "standard_price": 1280,
            "spare_classification": {"material_type": "spare", "abc": "A", "ved": "V", "fsn": "F", "reason": "关键设备主轴备件，按消耗、关键性与流动性综合评审"},
        },
    )
    assert material.status_code == 201, material.text
    equipment = client.post(
        "/api/v1/equipment",
        headers=MANAGER,
        json={
            "code": f"EQ-{tag}",
            "name": "五轴加工中心",
            "factory_code": factory.json()["code"],
            "location": "一号车间",
            "model": "CNC-500",
            "criticality": "high",
            "responsible_person": "张工",
        },
    )
    assert equipment.status_code == 201, equipment.text
    return factory.json(), material.json(), equipment.json()


def test_equipment_mro_to_requisition_closed_loop() -> None:
    factory, material, equipment = create_fixture()
    equipment_id = equipment["id"]

    bom = client.post(
        f"/api/v1/equipment/{equipment_id}/bom",
        headers=MANAGER,
        json={"material_id": material["id"], "quantity": 1, "replacement_cycle_days": 180, "safety_quantity": 2, "critical": True},
    )
    assert bom.status_code == 201, bom.text
    assert client.post(f"/api/v1/equipment/{equipment_id}/bom", headers=MANAGER, json={"material_id": material["id"]}).status_code == 409

    plan = client.post(
        f"/api/v1/equipment/{equipment_id}/maintenance-plans",
        headers=MANAGER,
        json={
            "name": "季度主轴维护",
            "plan_type": "preventive",
            "interval_days": 90,
            "next_due_date": (date.today() + timedelta(days=20)).isoformat(),
            "material_code": material["code"],
            "planned_quantity": 2,
            "owner": "李工",
        },
    )
    assert plan.status_code == 201, plan.text

    faults = []
    for occurred, restored in (
        ("2026-01-01T08:00:00", "2026-01-01T12:00:00"),
        ("2026-01-11T08:00:00", "2026-01-11T10:00:00"),
    ):
        response = client.post(
            f"/api/v1/equipment/{equipment_id}/faults",
            headers=MANAGER,
            json={
                "occurred_at": occurred,
                "restored_at": restored,
                "fault_category": "主轴异常",
                "cause": "轴承磨损",
                "action": "更换轴承并复测",
                "material_code": material["code"],
                "quantity_used": 1,
                "status": "closed",
                "reported_by": "王工",
            },
        )
        assert response.status_code == 201, response.text
        faults.append(response.json())

    reliability = client.get(f"/api/v1/equipment/{equipment_id}/reliability").json()
    assert reliability["failure_count"] == 2
    assert reliability["mtbf_hours"] == 240

    request = {"equipment_id": equipment_id, "horizon_days": 90, "selected_material_codes": [material["code"]]}
    analyzed = client.post("/api/v1/mro-net-requirements/analyze", json=request)
    assert analyzed.status_code == 200, analyzed.text
    line = analyzed.json()["items"][0]
    assert line["planned_demand"] == 2
    assert line["corrective_demand"] == 9
    assert line["net_requirement"] == 13
    assert line["evidence"]["mtbf_hours"] == 240

    created = client.post("/api/v1/mro-net-requirements/create-requisition", headers=MANAGER, json=request)
    assert created.status_code == 201, created.text
    requisition = created.json()["requisition"]
    assert requisition["status"] == "draft"
    assert requisition["lines"][0]["quantity"] == "13.0000"
    listed = client.get(f"/api/v1/requisitions?keyword={equipment['code']}").json()
    assert listed["total"] == 1

    assert client.patch(f"/api/v1/equipment-faults/{faults[0]['id']}", headers=MANAGER, json={"occurred_at": "2026-01-01T08:00:00", "restored_at": "2026-01-01T13:00:00", "status": "closed"}).status_code == 200
    assert client.patch(f"/api/v1/maintenance-plans/{plan.json()['id']}", headers=MANAGER, json={**plan.json(), "name": "更新后的季度主轴维护"}).status_code == 200
    assert client.patch(f"/api/v1/equipment-bom/{bom.json()['id']}", headers=MANAGER, json={**bom.json(), "quantity": 2}).status_code == 200
    assert client.delete(f"/api/v1/materials/{material['id']}", headers=MANAGER).status_code == 409
    assert client.delete(f"/api/v1/factories/{factory['id']}", headers=MANAGER).status_code == 409
    assert client.delete(f"/api/v1/equipment/{equipment_id}", headers=MANAGER).status_code == 409


def test_mro_validation_permissions_and_empty_evidence() -> None:
    _, material, equipment = create_fixture()
    equipment_id = equipment["id"]
    assert client.post("/api/v1/equipment", headers=MANAGER, json={"code": "UNKNOWN-EQ", "name": "未知工厂设备", "factory_code": "NOT-EXISTS"}).status_code == 422
    assert client.post(f"/api/v1/equipment/{equipment_id}/bom", headers=ANALYST, json={"material_id": material["id"]}).status_code == 403
    invalid_fault = client.post(
        f"/api/v1/equipment/{equipment_id}/faults",
        headers=MANAGER,
        json={"occurred_at": "2026-03-02T08:00:00", "restored_at": "2026-03-01T08:00:00", "status": "closed"},
    )
    assert invalid_fault.status_code == 422
    analyzed = client.post("/api/v1/mro-net-requirements/analyze", json={"equipment_id": equipment_id, "horizon_days": 30}).json()
    assert analyzed["items"] == []
    assert len(analyzed["warnings"]) == 2
    assert client.post("/api/v1/mro-net-requirements/create-requisition", headers=MANAGER, json={"equipment_id": equipment_id, "horizon_days": 30}).status_code == 409
    assert client.delete(f"/api/v1/equipment/{equipment_id}", headers=MANAGER).status_code == 204
