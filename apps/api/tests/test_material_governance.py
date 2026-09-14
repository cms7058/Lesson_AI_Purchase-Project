from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_duplicate_scan_and_review():
    headers = {"X-User-Id": "manager-governance", "X-User-Role": "procurement_manager"}
    first = client.post("/api/v1/materials", headers=headers, json={"code": "GOV-A", "name": "深沟球轴承", "specification": "6205 2RS", "category": "轴承", "unit": "件", "spare_classification": {"material_type": "production", "abc": "B", "ved": "E", "fsn": "S", "reason": ""}}).json()
    second = client.post("/api/v1/materials", headers=headers, json={"code": "GOV-B", "name": "深沟球轴承", "specification": "6205-2RS", "category": "轴承", "unit": "件", "spare_classification": {"material_type": "production", "abc": "B", "ved": "E", "fsn": "S", "reason": ""}}).json()
    result = client.get("/api/v1/material-governance/duplicates", params={"keyword": "GOV-", "threshold": 0.6}).json()
    pair = next(item for item in result["items"] if {item["left"]["code"], item["right"]["code"]} == {"GOV-A", "GOV-B"})
    assert pair["similarity"] > 0.9
    assert pair["status"] == "unreviewed"
    response = client.post("/api/v1/material-governance/duplicate-decisions", headers=headers, json={"left_material_id": first["id"], "right_material_id": second["id"], "similarity": pair["similarity"], "status": "duplicate", "master_material_id": first["id"], "basis": pair["basis"], "note": "测试确认"})
    assert response.status_code == 200
    reviewed = client.get("/api/v1/material-governance/duplicates", params={"keyword": "GOV-", "threshold": 0.6, "decision_status": "duplicate"}).json()
    assert reviewed["total"] == 1
    assert reviewed["items"][0]["master_material_id"] == first["id"]


def test_duplicate_review_requires_manager():
    response = client.post("/api/v1/material-governance/duplicate-decisions", headers={"X-User-Id": "buyer", "X-User-Role": "buyer"}, json={"left_material_id": "a", "right_material_id": "b", "similarity": 0.8, "status": "watchlist"})
    assert response.status_code == 403
