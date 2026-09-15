from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app

HEADERS = {"X-User-Role": "procurement_manager", "X-User-Id": "aviation-demo-manager"}


def test_aviation_demo_profiles_and_hard_gate():
    with TestClient(app) as client:
        seeded = client.post("/api/v1/aviation-mro/demo", headers=HEADERS)
        assert seeded.status_code == 200, seeded.text
        assert seeded.json()["result"]["materials"] == 12

        profile = client.get("/api/v1/aviation-mro/materials/DEMO-AERO-004", headers=HEADERS)
        assert profile.status_code == 200
        assert profile.json()["part_number"] == "AERO-DEMO-PN-004"
        assert "8130-3" in profile.json()["certificate_requirements"]

        context = client.get(
            "/api/v1/strategy-decisions/DEMO-AERO-004/context", headers=HEADERS
        ).json()
        assert context["aviation"]["ata_chapter"] == "29"
        qualified_supplier = next(
            row
            for row in context["supplier_capabilities"]
            if row["relationship_status"] == "qualified"
        )

        today = datetime.now(UTC).date()
        common = {
            "quantity": 1,
            "required_date": str(today + timedelta(days=5)),
            "budget": 100000,
            "baseline_price": 68000,
            "premium_limit": 50,
            "risk_limit": 20,
            "downtime_per_day": 20000,
            "annual_issues": 2,
            "critical": True,
            "reserve": 0,
            "available": 0,
            "inventory_confirmed": True,
            "owner": "航空采购经理",
            "evidence": "教学场景需求单与库存快照",
        }
        base_candidate = {
            "supplier_id": qualified_supplier["supplier_id"],
            "source": "oem",
            "supply_mode": "standard",
            "fees": 0,
            "holding_cost": 0,
            "validation_cost": 0,
            "arrival": str(today + timedelta(days=3)),
            "validated": True,
            "reliability": 98,
            "evidence": "教学报价与适航资料清单",
            "offer_type": "purchase",
            "condition": "NEW",
            "repair_cost": 0,
            "core_charge": 0,
            "core_credit": 0,
            "return_penalty": 0,
            "available_quantity": 5,
            "minimum_order_quantity": 1,
            "package_quantity": 1,
        }
        payload = {
            **common,
            "candidates": [
                {
                    **base_candidate,
                    "name": "低价但资料缺失",
                    "unit_price": 50000,
                    "certificate_status": "missing",
                    "trace_status": "incomplete",
                    "applicability_status": "not_verified",
                    "remaining_life_percent": 20,
                },
                {
                    **base_candidate,
                    "name": "适航资料完整",
                    "unit_price": 70000,
                    "certificate_status": "verified",
                    "trace_status": "complete",
                    "applicability_status": "verified",
                    "remaining_life_percent": 100,
                },
            ],
        }
        result = client.post(
            "/api/v1/strategy-decisions/DEMO-AERO-004/preview",
            headers=HEADERS,
            json=payload,
        )
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["recommendation"] == "适航资料完整"
        assert data["candidates"][0]["eligible"] is False
        assert {"适航证书缺失", "追溯链不完整", "适用性未确认", "剩余寿命不足"} <= set(
            data["candidates"][0]["issues"]
        )
        assert data["process"][1]["name"] == "适航硬门槛"

        aog_payload = {
            **payload,
            "demand_type": "aog",
            "required_within_hours": 1,
            "candidates": [{**payload["candidates"][1], "name": "响应超时方案"}],
        }
        aog_result = client.post(
            "/api/v1/strategy-decisions/DEMO-AERO-004/preview",
            headers=HEADERS,
            json=aog_payload,
        ).json()
        assert aog_result["recommendation"] is None
        assert "响应时限冲突" in aog_result["candidates"][0]["issues"]
