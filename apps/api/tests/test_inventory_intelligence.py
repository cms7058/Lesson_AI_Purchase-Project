from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
MANAGER = {"X-User-Id": "inventory-manager", "X-User-Role": "procurement_manager"}
ANALYST = {"X-User-Id": "inventory-analyst", "X-User-Role": "analyst"}


def fixture() -> tuple[dict, dict, dict]:
    tag = uuid4().hex[:8]
    material = client.post(
        "/api/v1/materials",
        headers=MANAGER,
        json={"code": f"INT-SP-{tag}", "name": "智能库存测试轴承", "standard_price": 100, "lead_time_days": 30, "spare_classification": {"material_type": "spare", "abc": "A", "ved": "V", "fsn": "F", "reason": "测试需求、库存和LCC计算"}},
    )
    assert material.status_code == 201, material.text
    supplier = client.post("/api/v1/suppliers", headers=MANAGER, json={"code": f"INT-S-{tag}", "name": "智能库存测试供应商"})
    assert supplier.status_code == 201, supplier.text
    warehouse = client.post("/api/v1/warehouses", headers=MANAGER, json={"code": f"INT-W-{tag}", "name": "智能库存测试仓"})
    assert warehouse.status_code == 201, warehouse.text
    location = client.post("/api/v1/warehouse-locations", headers=MANAGER, json={"warehouse_code": warehouse.json()["code"], "code": "A-01", "name": "测试库位"})
    assert location.status_code == 201, location.text
    stock = client.post(
        "/api/v1/spare-stocks",
        headers=MANAGER,
        json={"warehouse_code": warehouse.json()["code"], "location_code": "A-01", "material_code": material.json()["code"], "material_name": material.json()["name"], "batch_no": "B-01", "quantity": 20, "safety_stock": 1, "min_stock": 2, "reorder_point": 3, "max_stock": 30},
    )
    assert stock.status_code == 201, stock.text
    movement = client.post(
        "/api/v1/warehouse-movements",
        headers=MANAGER,
        json={"movement_type": "issue", "warehouse_code": warehouse.json()["code"], "from_location": "A-01", "material_code": material.json()["code"], "material_name": material.json()["name"], "batch_no": "B-01", "quantity": 4, "business_no": "WO-TEST-001"},
    )
    assert movement.status_code == 201, movement.text
    return material.json(), supplier.json(), stock.json()


def test_inventory_recommendation_lcc_apply_and_history() -> None:
    material, supplier, stock = fixture()
    agreement_payload = {"material_code": material["code"], "supplier_code": supplier["code"], "mode": "vmi", "ownership": "supplier", "replenishment_rule": "低于再订货点后24小时内补至最高库存", "settlement_trigger": "维修领用后按月结算", "min_quantity": 2, "max_quantity": 12, "response_hours": 24, "service_level": 97, "effective_from": "2026-01-01", "effective_to": "2027-12-31", "status": "active", "evidence": "VMI-TEST-001测试协议及补货责任说明"}
    agreement = client.post("/api/v1/supply-collaborations", headers=MANAGER, json=agreement_payload)
    assert agreement.status_code == 201, agreement.text
    assert agreement.json()["supplier_name"] == supplier["name"]

    body = {"scenario_name": "五年VMI基准", "service_level": 97, "review_days": 30, "horizon_years": 5, "logistics_cost": 500, "annual_maintenance_cost": 200, "downtime_cost": 3000, "disposal_cost": 100, "residual_value": 50, "annual_holding_rate": 18, "save": True}
    response = client.post(f"/api/v1/inventory-intelligence/{material['code']}/analyze", headers=MANAGER, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["evidence"]["actual_consumption"] == 4
    assert result["evidence"]["annual_demand"] == 4
    assert result["parameters"]["safety_stock"] <= result["parameters"]["min_stock"] <= result["parameters"]["reorder_point"] <= result["parameters"]["max_stock"]
    assert result["lcc"]["total"] == sum(result["lcc"]["parts"].values())
    assert result["collaborations"][0]["mode"] == "vmi"
    assert result["analysis_id"]

    history = client.get(f"/api/v1/inventory-intelligence/{material['code']}/history?page=1&page_size=10").json()
    assert history["total"] == 1
    assert history["items"][0]["scenario_name"] == "五年VMI基准"
    parameters = result["parameters"]
    applied = client.post(
        f"/api/v1/inventory-intelligence/{material['code']}/apply-parameters",
        headers=MANAGER,
        json={"stock_ids": [stock["id"]], "safety_stock": parameters["safety_stock"], "min_stock": parameters["min_stock"], "reorder_point": parameters["reorder_point"], "max_stock": parameters["max_stock"]},
    )
    assert applied.status_code == 200, applied.text
    listed = client.get(f"/api/v1/spare-stocks?keyword={material['code']}").json()["items"][0]
    assert float(listed["reorder_point"]) == parameters["reorder_point"]

    updated = client.put(f"/api/v1/supply-collaborations/{agreement.json()['id']}", headers=MANAGER, json={**agreement_payload, "version": agreement.json()["version"], "response_hours": 12})
    assert updated.status_code == 200
    assert updated.json()["response_hours"] == 12
    assert client.delete(f"/api/v1/supply-collaborations/{agreement.json()['id']}?version={updated.json()['version']}", headers=MANAGER).status_code == 204


def test_inventory_intelligence_validation_and_permissions() -> None:
    material, supplier, stock = fixture()
    invalid = {"material_code": material["code"], "supplier_code": supplier["code"], "mode": "shared_stock", "replenishment_rule": "按需补货", "settlement_trigger": "领用", "min_quantity": 10, "max_quantity": 2, "evidence": "测试"}
    assert client.post("/api/v1/supply-collaborations", headers=MANAGER, json=invalid).status_code == 422
    assert client.post("/api/v1/supply-collaborations", headers=ANALYST, json={**invalid, "min_quantity": 1, "max_quantity": 2}).status_code == 403
    result = client.post(f"/api/v1/inventory-intelligence/{material['code']}/analyze", headers=ANALYST, json={"scenario_name": "只读预览", "save": False})
    assert result.status_code == 200
    assert client.post(f"/api/v1/inventory-intelligence/{material['code']}/analyze", headers=ANALYST, json={"scenario_name": "禁止保存", "save": True}).status_code == 403
    bad_apply = client.post(f"/api/v1/inventory-intelligence/{material['code']}/apply-parameters", headers=MANAGER, json={"stock_ids": [stock["id"]], "safety_stock": 5, "min_stock": 4, "reorder_point": 3, "max_stock": 2})
    assert bad_apply.status_code == 422
