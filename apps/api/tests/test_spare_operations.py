from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_spare_strategy_and_warehouse_closed_loop():
    h = {"X-User-Id": "warehouse-manager", "X-User-Role": "procurement_manager"}
    suffix = uuid4().hex[:8]
    with TestClient(app) as client:
        material_code = f"SP-WH-{suffix}"
        material = client.post("/api/v1/materials", headers=h, json={"code": material_code, "name": "测试密封件", "spare_classification": {"material_type": "spare", "abc": "B", "ved": "V", "fsn": "S", "reason": "仓储闭环测试"}})
        assert material.status_code == 201, material.text

        strategy = client.post("/api/v1/spare-strategies", headers=h, json={"name": "关键密封件国产替代", "material_code": material_code, "source_mode": "domestic", "supplier_model": "vmi", "urgency": "planned", "price_baseline": 100, "premium_limit": 10, "lead_time_days": 7, "rationale": "降低原厂依赖并设置双供"})
        assert strategy.status_code == 201, strategy.text
        strategy_row = strategy.json()
        strategy_row["decision_status"] = "approved"
        assert client.put(f"/api/v1/spare-strategies/{strategy_row['id']}", headers=h, json=strategy_row).json()["version"] == 2

        warehouse = client.post("/api/v1/warehouses", headers=h, json={"code": f"WH-{suffix}", "name": "维修备件库", "factory_code": "F01", "manager": "张仓管"})
        assert warehouse.status_code == 201, warehouse.text
        location = client.post("/api/v1/warehouse-locations", headers=h, json={"warehouse_code": f"WH-{suffix}", "code": "FAST-01", "name": "维修区快速库位", "zone_type": "fast", "near_maintenance": True})
        assert location.status_code == 201, location.text
        stock = client.post("/api/v1/spare-stocks", headers=h, json={"warehouse_code": f"WH-{suffix}", "location_code": "FAST-01", "material_code": material_code, "material_name": "测试密封件", "batch_no": "B001", "quantity": 10, "safety_stock": 2, "min_stock": 3, "reorder_point": 5, "max_stock": 30, "planned_reserve": 2})
        assert stock.status_code == 201, stock.text
        stock_id = stock.json()["id"]

        issue = client.post("/api/v1/warehouse-movements", headers=h, json={"movement_type": "issue", "warehouse_code": f"WH-{suffix}", "from_location": "FAST-01", "material_code": material_code, "material_name": "测试密封件", "batch_no": "B001", "quantity": 6, "business_no": "WO-001"})
        assert issue.status_code == 201, issue.text
        current = client.get("/api/v1/spare-stocks", headers=h, params={"keyword": material_code}).json()["items"][0]
        assert float(current["quantity"]) == 4

        take = client.post("/api/v1/stocktakes", headers=h, json={"stock_id": stock_id, "counted_quantity": 3, "reason": "月度盘点"})
        assert take.status_code == 201 and float(take.json()["variance"]) == -1
        soh = client.post("/api/v1/soh-inspections", headers=h, json={"stock_id": stock_id, "rust_score": 55, "moisture_score": 60, "dust_score": 60, "packaging_score": 55, "action": "隔离并重新防锈包装"})
        assert soh.status_code == 201 and soh.json()["conclusion"] == "quarantine"
        summary = client.get("/api/v1/warehouse/summary", headers=h).json()
        assert summary["reorder_alerts"] >= 1 and summary["soh_alerts"] >= 1
