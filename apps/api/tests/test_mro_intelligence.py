from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

HEADERS = {"X-User-Role": "procurement_manager", "X-User-Id": "mro-planner"}


def test_seller_led_mro_forecast_inventory_and_calendar():
    with TestClient(app) as client:
        seeded = client.post("/api/v1/mro-intelligence/demo", headers=HEADERS)
        assert seeded.status_code == 200, seeded.text

        profiles = client.get("/api/v1/mro-intelligence/profiles?page_size=100", headers=HEADERS)
        assert profiles.status_code == 200
        assert profiles.json()["total"] >= 6
        critical = next(
            item for item in profiles.json()["items"] if item["material_code"] == "DEMO-AERO-004"
        )
        assert {"单一来源", "长交期", "高价值", "停场关键"} <= {
            item["label"] for item in critical["attributes"]
        }

        response = client.post(
            "/api/v1/mro-intelligence/analyze",
            headers=HEADERS,
            json={"horizon_days": 180, "material_codes": [], "save": True},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        hydraulic = next(
            item for item in result["items"] if item["material_code"] == "DEMO-AERO-004"
        )
        assert hydraulic["forecast_method"] == "amos_event_inference"
        assert hydraulic["inventory_breakdown"]["consignment"] == 1
        assert hydraulic["diagnostics"]["demand"]["count"] >= 8
        assert "median" in hydraulic["diagnostics"]["lead_time"]
        assert {event["plan_type"] for event in result["calendar_events"]} == {
            "purchase",
            "supply",
        }
        assert result["run_id"]


def test_mro_connector_types_are_configurable():
    with TestClient(app) as client:
        tag = uuid4().hex[:8]
        for connector_type in ("amos", "sap", "consignment", "vmi"):
            response = client.post(
                "/api/v1/data-connectors",
                headers=HEADERS,
                json={
                    "name": f"MRO-{connector_type}-{tag}",
                    "connector_type": connector_type,
                    "base_url": "https://example.com/api",
                    "sync_mode": "scheduled",
                },
            )
            assert response.status_code == 201, response.text


def test_mro_calendar_executes_picking_task_and_purchase_order():
    with TestClient(app) as client:
        client.post("/api/v1/mro-intelligence/demo", headers=HEADERS)
        analysis = client.post(
            "/api/v1/mro-intelligence/analyze",
            headers=HEADERS,
            json={"horizon_days": 180, "material_codes": [], "save": True},
        ).json()
        event = next(item for item in analysis["calendar_events"] if item["plan_type"] == "purchase")
        inventory = client.post(
            "/api/v1/mro-intelligence/inventory-status",
            headers=HEADERS,
            json={"material_codes": [event["material_code"]]},
        )
        assert inventory.status_code == 200, inventory.text
        assert inventory.json()["items"][0]["available_quantity"] > 0

        base = {
            "plan_run_id": analysis["run_id"],
            "plan_event_id": event["id"],
            "material_code": event["material_code"],
            "material_name": event["material_name"],
            "quantity": 1,
            "plan_date": event["date"],
        }
        supply = client.post(
            "/api/v1/mro-intelligence/execute",
            headers=HEADERS,
            json=base | {"action_type": "activate_supply"},
        )
        assert supply.status_code == 200, supply.text
        assert supply.json()["execution"]["reference_no"].startswith("PICK-MRO-")
        tasks = client.get("/api/v1/warehouse-picking-tasks", headers=HEADERS).json()
        assert any(row["material_code"] == event["material_code"] for row in tasks["items"])

        order = client.post(
            "/api/v1/mro-intelligence/execute",
            headers=HEADERS,
            json=base | {"action_type": "create_order"},
        )
        assert order.status_code == 200, order.text
        assert order.json()["execution"]["reference_no"].startswith("PO-")
        orders = client.get("/api/v1/orders", headers=HEADERS).json()
        assert any(row["order_no"] == order.json()["execution"]["reference_no"] for row in orders["items"])


def test_mro_ingest_is_validated_and_idempotent():
    with TestClient(app) as client:
        client.post("/api/v1/mro-intelligence/demo", headers=HEADERS)
        tag = uuid4().hex[:8]
        payload = {
            "demand_events": [
                {
                    "material_code": "DEMO-AERO-004",
                    "event_date": "2027-03-01",
                    "quantity": 2,
                    "demand_type": "planned",
                    "probability": 1,
                    "confirmed": True,
                    "source_system": "AMOS",
                    "source_ref": f"AMOS-WP-{tag}",
                    "evidence": "测试维修包",
                }
            ],
            "supply_positions": [
                {
                    "material_code": "DEMO-AERO-004",
                    "position_type": "vmi",
                    "warehouse_code": "VMI-TEST",
                    "quantity": 1,
                    "source_system": "VMI",
                    "source_ref": f"VMI-POS-{tag}",
                }
            ],
            "lead_time_samples": [
                {
                    "material_code": "DEMO-AERO-004",
                    "supplier_name": "测试供应商",
                    "transaction_type": "purchase",
                    "days": 188,
                    "happened_date": "2026-08-01",
                    "source_system": "SAP",
                    "source_ref": f"SAP-PO-{tag}",
                }
            ],
        }
        first = client.post("/api/v1/mro-intelligence/ingest", headers=HEADERS, json=payload)
        assert first.status_code == 200, first.text
        assert first.json()["accepted"] == {
            "demand_events": 1,
            "supply_positions": 1,
            "lead_time_samples": 1,
        }
        repeated = client.post("/api/v1/mro-intelligence/ingest", headers=HEADERS, json=payload)
        assert repeated.status_code == 200
        assert repeated.json()["duplicates"] == {
            "demand_events": 1,
            "supply_positions": 1,
            "lead_time_samples": 1,
        }

        schema = client.get("/api/v1/mro-intelligence/integration-schema").json()
        assert {"AMOS", "SAP", "WMS", "CONSIGNMENT", "VMI"} <= set(schema["systems"])
