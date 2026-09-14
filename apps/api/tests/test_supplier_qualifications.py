from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
MANAGER = {"X-User-Id": "qualification-manager", "X-User-Role": "procurement_manager"}
BUYER = {"X-User-Id": "qualification-buyer", "X-User-Role": "buyer"}


def test_supplier_qualification_crud_attachment_review_expiry_and_history():
    tag = uuid4().hex[:8]
    today = datetime.now(UTC).date()
    supplier = client.post("/api/v1/suppliers", headers=MANAGER, json={"code": "QUAL-" + tag, "name": "资质测试供应商"}).json()
    payload = {
        "qualification_type": "ISO 9001质量管理体系",
        "certificate_no": "ISO-" + tag,
        "issuing_authority": "测试认证机构",
        "valid_from": today.isoformat(),
        "expires_on": (today + timedelta(days=20)).isoformat(),
        "review_note": "用于自动化测试",
    }
    assert client.post(f"/api/v1/suppliers/{supplier['id']}/qualifications", headers=BUYER, json=payload).status_code == 403
    created = client.post(f"/api/v1/suppliers/{supplier['id']}/qualifications", headers=MANAGER, json=payload)
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["effective_status"] == "pending" and item["version"] == 1

    decision_url = f"/api/v1/supplier-qualifications/{item['id']}/decision"
    assert client.post(decision_url, headers=MANAGER, json={"status": "approved", "note": ""}).status_code == 409
    upload_url = f"/api/v1/supplier-qualifications/{item['id']}/attachment"
    assert client.post(upload_url, headers=MANAGER, files={"file": ("bad.exe", b"x")}).status_code == 422
    uploaded = client.post(upload_url, headers=MANAGER, files={"file": ("iso9001.pdf", b"%PDF-1.4 test qualification")})
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["attachment_name"] == "iso9001.pdf" and uploaded.json()["version"] == 2
    download = client.get(f"/api/v1/supplier-qualifications/{item['id']}/attachment", headers=BUYER)
    assert download.status_code == 200 and download.content.startswith(b"%PDF")

    approved = client.post(decision_url, headers=MANAGER, json={"status": "approved", "note": "已核验证书原件"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["effective_status"] == "expiring"
    listed = client.get("/api/v1/supplier-qualifications", params={"supplier_id": supplier["id"], "effective_status": "expiring", "page_size": 10}).json()
    assert listed["total"] == 1 and listed["counts"]["expiring"] == 1

    changed = client.patch(f"/api/v1/supplier-qualifications/{item['id']}", headers=MANAGER, json={**payload, "expires_on": (today + timedelta(days=400)).isoformat()})
    assert changed.status_code == 200 and changed.json()["review_status"] == "pending" and changed.json()["version"] == 3
    history = client.get(f"/api/v1/supplier-qualifications/{item['id']}/history", params={"page": 1, "page_size": 10}).json()
    assert history["total"] == 4
    assert {row["action"] for row in history["items"]} == {"create", "attachment", "review", "update"}

    assert client.delete(f"/api/v1/suppliers/{supplier['id']}", headers=MANAGER).status_code == 409
    assert client.delete(f"/api/v1/supplier-qualifications/{item['id']}", headers=BUYER).status_code == 403
    assert client.delete(f"/api/v1/supplier-qualifications/{item['id']}", headers=MANAGER).status_code == 204
    assert client.get("/api/v1/supplier-qualifications", params={"supplier_id": supplier["id"]}).json()["total"] == 0
    assert client.delete(f"/api/v1/suppliers/{supplier['id']}", headers=MANAGER).status_code == 204


def test_qualification_date_validation_and_missing_resources():
    bad = {"qualification_type": "测试资质", "valid_from": "2027-01-02", "expires_on": "2027-01-01"}
    assert client.post("/api/v1/suppliers/missing/qualifications", headers=MANAGER, json=bad).status_code == 422
    assert client.get("/api/v1/supplier-qualifications/missing/history").status_code == 404
