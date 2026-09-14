import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import supplier_portal
from app.core.database import SessionLocal
from app.domain.supplier_portal import MailSettings, RFQMail
from app.main import app
from app.services import rfq_mail

client = TestClient(app)
HEADERS = {"X-User-Role": "procurement_manager", "X-User-Id": "portal-test"}
ADMIN = {"X-User-Role": "admin", "X-User-Id": "admin-test"}


@pytest.fixture
def scenario(monkeypatch, tmp_path):
    monkeypatch.setattr(supplier_portal, "FILES", tmp_path)
    monkeypatch.setenv("PEBS_SECRET_KEY", Fernet.generate_key().decode())
    tag = uuid4().hex[:8]
    suppliers = []
    sessions = []
    for i in range(3):
        s = client.post("/api/v1/suppliers", headers=HEADERS, json={"code": f"PORTAL-{tag}-{i}", "name": f"门户供应商{i}", "email": f"s{i}@example.invalid", "status": "qualified"}).json()
        username = f"portal-{tag}-{i}"
        result = client.put("/api/v1/supplier-accounts", headers=ADMIN, json={"supplier_id": s["id"], "username": username, "password": "Test-password-123!"})
        assert result.status_code == 200, result.text
        logged = client.post("/api/v1/supplier/login", json={"username": username, "password": "Test-password-123!"})
        assert logged.status_code == 200, logged.text
        suppliers.append(s)
        sessions.append({"Authorization": f"Bearer {logged.json()['token']}"})
    rfq = client.post("/api/v1/rfqs", headers=HEADERS, json={"title": f"门户询价{tag}", "deadline": str(datetime.now(UTC).date()+timedelta(days=30)), "lines": [{"material_code": "MAT-P", "material_name": "精密件", "quantity": 20, "unit": "件"}], "invitations": [{"supplier_id": s["code"], "supplier_name": s["name"]} for s in suppliers]}).json()
    return rfq, suppliers, sessions


def publish(rfq):
    response = client.post(f"/api/v1/rfqs/{rfq['id']}/publish", headers=HEADERS)
    assert response.status_code == 200, response.text


def test_supplier_combined_filters_keep_invitation_scope(scenario):
    rfq, _, sessions = scenario
    publish(rfq)
    filters = [{"field":"rfq_no","op":"eq","value":rfq["rfq_no"]},{"field":"material_code","op":"eq","value":"MAT-P"}]
    response = client.get("/api/v1/supplier/rfqs",headers=sessions[0],params={"filters":json.dumps(filters),"page_size":1})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert client.get("/api/v1/supplier/rfqs",params={"filters":json.dumps(filters)}).status_code == 401
    filters.append({"field":"supplier_id","op":"eq","value":"other"})
    assert client.get("/api/v1/supplier/rfqs",headers=sessions[0],params={"filters":json.dumps(filters)}).status_code == 422


@pytest.mark.parametrize("role", ["procurement_manager", "buyer", "analyst", "auditor"])
def test_supplier_accounts_admin_only(role):
    headers = {"X-User-Role": role}
    assert client.get("/api/v1/supplier-accounts", headers=headers).status_code == 403
    assert client.get("/api/v1/supplier-accounts/portal", headers=headers).status_code == 403
    assert client.put("/api/v1/supplier-accounts", headers=headers, json={"supplier_id":"not-found", "username":"forbidden", "password":"Forbidden-test-123"}).status_code == 403
    assert client.get("/api/v1/identity", headers=headers).json()["role"] == role


def test_admin_account_directory_and_portal():
    assert client.get("/api/v1/supplier-accounts", headers=ADMIN).status_code == 200
    assert client.get("/api/v1/supplier-accounts/portal", headers=ADMIN).status_code == 200
    assert client.get("/api/v1/supplier-accounts").status_code == 403


def test_supplier_quote_auto_response_and_privacy(scenario):
    rfq, _, sessions = scenario
    url = f"/api/v1/supplier/rfqs/{rfq['id']}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=sessions[0]).status_code == 404
    publish(rfq)
    for i in range(2):
        bid = client.post(url+"/quote", headers=sessions[i], json={"delivery_days": 10+i, "lines": [{"unit_price": 100+i, "tax_rate": 0.13}]})
        assert bid.status_code == 201, bid.text
        duplicate = client.post(url+"/quote", headers=sessions[i], json={"delivery_days": 10, "lines": [{"unit_price": 1}]})
        assert duplicate.status_code == 409
    rows = client.get(f"/api/v1/rfqs/{rfq['id']}/bids", headers=HEADERS).json()["items"]
    assert len(rows) == 3 and sum(bool(r["quotation"]) for r in rows) == 2
    details = client.get(url, headers=sessions[2]).json()
    assert "invitations" not in details and "awarded_quotation_id" not in details
    assert details["quotation"] is None
    own = client.get(url, headers=sessions[0]).json()
    assert float(own["quotation"]["lines"][0]["unit_price"]) == 100
    history = client.get("/api/v1/supplier/rfqs?tab=history&page_size=1", headers=sessions[0]).json()
    assert history["total"] == 1 and len(history["items"]) == 1
    assert client.get("/api/v1/supplier/rfqs?tab=pending", headers=sessions[0]).json()["total"] == 0
    client.post("/api/v1/supplier/logout", headers=sessions[0])
    assert client.get(url, headers=sessions[0]).status_code == 401


def test_buyer_reviews_supplier_quote_with_cost_summary(scenario):
    rfq, _, sessions = scenario
    publish(rfq)
    quote = client.post(
        f"/api/v1/supplier/rfqs/{rfq['id']}/quote",
        headers=sessions[0],
        json={"delivery_days": 8, "validity_days": 45, "source_type": "ocr", "lines": [{"unit_price": 100, "tax_rate": 0.13, "logistics_cost": 15}]},
    )
    assert quote.status_code == 201, quote.text
    quote_id = quote.json()["id"]
    bids = client.get(f"/api/v1/rfqs/{rfq['id']}/bids", headers=HEADERS)
    assert bids.status_code == 200, bids.text
    row = next(item for item in bids.json()["items"] if item["quotation"])
    assert row["quotation"]["source_type"] == "ocr"
    assert float(row["cost_summary"]["landed_total"]) == 2275
    assert row["review"]["status"] == "pending"
    pending_analysis = client.get(f"/api/v1/rfqs/{rfq['id']}/award-analysis", headers=HEADERS).json()
    assert pending_analysis["quoted_count"] == 1
    assert pending_analysis["verified_count"] == 0
    assert pending_analysis["lowest_ids"] == []
    review_url = f"/api/v1/rfqs/{rfq['id']}/quotations/{quote_id}/review"
    assert client.put(review_url, headers=HEADERS, json={"status": "rejected", "note": ""}).status_code == 422
    rejected = client.put(review_url, headers=HEADERS, json={"status": "rejected", "note": "价格需重新核实"})
    assert rejected.status_code == 200, rejected.text
    pending = client.get("/api/v1/supplier/rfqs?tab=pending", headers=sessions[0]).json()
    returned = next(item for item in pending["items"] if item["id"] == rfq["id"])
    assert returned["review_status"] == "rejected" and returned["responded"] is False
    detail = client.get(f"/api/v1/supplier/rfqs/{rfq['id']}", headers=sessions[0]).json()
    assert detail["review"] == {"status": "rejected", "note": "价格需重新核实"}
    revised = client.post(
        f"/api/v1/supplier/rfqs/{rfq['id']}/quote",
        headers=sessions[0],
        json={"delivery_days": 7, "source_type": "manual", "lines": [{"unit_price": 101, "tax_rate": 0.13, "logistics_cost": 10}]},
    )
    assert revised.status_code == 201, revised.text
    revised_id = revised.json()["id"]
    assert revised_id != quote_id
    accepted = client.put(f"/api/v1/rfqs/{rfq['id']}/quotations/{revised_id}/review", headers=HEADERS, json={"status": "verified", "note": "已核对原始报价附件"})
    assert accepted.status_code == 200, accepted.text
    refreshed = client.get(f"/api/v1/rfqs/{rfq['id']}/bids", headers=HEADERS).json()
    reviewed = next(item for item in refreshed["items"] if item["quotation"])
    assert reviewed["review"]["status"] == "verified"
    assert reviewed["review"]["reviewer_id"] == "portal-test"
    assert len(reviewed["revision_history"]) == 2
    assert [item["version"] for item in reviewed["revision_history"]] == [1, 2]
    assert reviewed["revision_history"][0]["review"]["status"] == "rejected"
    assert reviewed["revision_history"][1]["current"] is True
    verified_analysis = client.get(f"/api/v1/rfqs/{rfq['id']}/award-analysis", headers=HEADERS).json()
    assert verified_analysis["lowest_ids"] == [revised_id]


def test_attachment_lifecycle_and_unauthorized_supplier(scenario):
    rfq, suppliers, sessions = scenario
    base = f"/api/v1/rfqs/{rfq['id']}"
    bad = client.post(base+"/attachments", headers=HEADERS, files={"file": ("run.exe", b"test")})
    assert bad.status_code == 422
    uploaded = client.post(base+"/attachments", headers=HEADERS, files={"file": ("spec.txt", b"material specification")})
    assert uploaded.status_code == 201, uploaded.text
    aid = uploaded.json()["id"]
    # Third supplier is removed before publishing; old session must not grant access.
    updated = client.patch(base, headers=HEADERS, json={"invitations": [{"supplier_id": suppliers[0]["code"], "supplier_name": suppliers[0]["name"]}]})
    assert updated.status_code == 200
    publish(rfq)
    url = f"/api/v1/supplier/rfqs/{rfq['id']}/attachments/{aid}"
    assert client.get(url, headers=sessions[0]).content == b"material specification"
    assert client.get(url, headers=sessions[2]).status_code == 404
    assert client.post(base+"/attachments", headers=HEADERS, files={"file": ("spec.txt", b"changed")}).status_code == 409
    assert client.delete(base+f"/attachments/{aid}", headers=HEADERS).status_code == 409


def test_expired_quotes_and_account_revocation(scenario):
    rfq, suppliers, sessions = scenario
    client.patch(f"/api/v1/rfqs/{rfq['id']}", headers=HEADERS, json={"deadline": str(datetime.now(UTC).date()-timedelta(days=2))})
    publish(rfq)
    result = client.post(f"/api/v1/supplier/rfqs/{rfq['id']}/quote", headers=sessions[0], json={"delivery_days": 10, "lines": [{"unit_price": 10}]})
    assert result.status_code == 409
    account = client.get("/api/v1/supplier-accounts?page_size=100", headers=ADMIN).json()["items"]
    row = next(a for a in account if a["supplier_id"] == suppliers[0]["id"])
    disabled = client.put("/api/v1/supplier-accounts", headers=ADMIN, json={**row, "active": False})
    assert disabled.status_code == 200
    assert client.get("/api/v1/supplier/rfqs", headers=sessions[0]).status_code == 401


def test_quotation_attachments_private_draft_and_submission_lock(scenario):
    rfq, _, sessions = scenario
    publish(rfq)
    base = f"/api/v1/supplier/rfqs/{rfq['id']}"
    upload = client.post(base+"/quotation-attachments", headers=sessions[0], files={"file": ("报价.txt", b"my private bid")})
    assert upload.status_code == 201, upload.text
    aid = upload.json()["id"]
    url = base+f"/quotation-attachments/{aid}"
    assert client.get(url, headers=sessions[0]).content == b"my private bid"
    assert client.get(url, headers=sessions[1]).status_code == 404
    assert client.delete(url, headers=sessions[1]).status_code == 404
    buyer_url = f"/api/v1/rfqs/{rfq['id']}/quotation-attachments/{aid}"
    assert client.get(buyer_url, headers=HEADERS).status_code == 404
    assert client.get(base, headers=sessions[1]).json()["quotation_attachments"] == []
    assert client.post(base+"/quote", headers=sessions[0], json={"delivery_days": 10, "lines": [{"unit_price": 10}]}).status_code == 201
    assert client.get(buyer_url, headers=HEADERS).content == b"my private bid"
    rows = client.get(f"/api/v1/rfqs/{rfq['id']}/bids", headers=HEADERS).json()["items"]
    assert rows[0]["quotation_attachments"][0]["id"] == aid
    assert client.delete(url, headers=sessions[0]).status_code == 409
    assert client.post(base+"/quotation-attachments", headers=sessions[0], files={"file": ("later.txt", b"late")}).status_code == 409
    assert client.get(base, headers=sessions[0]).json()["quotation_attachments"][0]["id"] == aid


def test_quotation_attachment_delete_and_validation(scenario):
    rfq, _, sessions = scenario
    base = f"/api/v1/supplier/rfqs/{rfq['id']}/quotation-attachments"
    assert client.post(base, headers=sessions[0], files={"file": ("a.txt", b"draft")}).status_code == 404
    publish(rfq)
    for name, content in [("a.exe", b"bad"), ("a.txt", b""), ("a.txt", b"x"*(10*1024*1024+1))]:
        assert client.post(base, headers=sessions[0], files={"file": (name, content)}).status_code == 422
    uploaded = client.post(base, headers=sessions[0], files={"file": ("a.txt", b"delete me")}).json()
    assert client.delete(base+"/"+uploaded["id"], headers=sessions[0]).status_code == 204
    assert client.get(base+"/"+uploaded["id"], headers=sessions[0]).status_code == 404


def test_quotation_attachment_extracts_prices_before_submission(scenario):
    rfq, _, sessions = scenario
    publish(rfq)
    base = f"/api/v1/supplier/rfqs/{rfq['id']}/quotation-attachments"
    content = "物料编码,未税单价,税率,物流费\nMAT-P,88.50,13%,120\n交期 9 天,有效期 45 天".encode()
    uploaded = client.post(base, headers=sessions[0], files={"file": ("供应商报价.csv", content)})
    assert uploaded.status_code == 201, uploaded.text
    result = client.post(f"{base}/{uploaded.json()['id']}/extract", headers=sessions[0])
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["confidence"] == 1
    assert data["delivery_days"] == 9
    assert data["validity_days"] == 45
    assert data["lines"][0]["material_code"] == "MAT-P"
    assert data["lines"][0]["unit_price"] == 88.5
    assert data["lines"][0]["tax_rate"] == 0.13
    assert data["lines"][0]["logistics_cost"] == 120
    assert data["requires_confirmation"] is True


def test_auto_mail_encrypted_password_and_no_duplicate_send(scenario, monkeypatch):
    rfq, _, _ = scenario
    sent = []
    failed_once = set()

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            pass

        def login(self, username, password):
            assert password == "smtp-secret-for-test"

        def send_message(self, msg):
            if msg["To"].startswith("s1@") and not failed_once:
                failed_once.add(msg["To"])
                raise rfq_mail.smtplib.SMTPException("transient failure")
            sent.append(msg)

    monkeypatch.setattr(rfq_mail.smtplib, "SMTP", SMTP)
    configured = client.put("/api/v1/mail-settings", headers=HEADERS, json={"host": "smtp.example.invalid", "from_email": "buyer@example.invalid", "username": "buyer", "password": "smtp-secret-for-test", "portal_url": "https://supplier.example.invalid/supplier", "auto_send": True})
    assert configured.status_code == 200, configured.text
    assert "smtp-secret-for-test" not in configured.text
    with SessionLocal() as db:
        assert "smtp-secret-for-test" not in db.get(MailSettings, 1).password_encrypted
    publish(rfq)
    assert len(sent) == 2
    retry = client.post(f"/api/v1/rfqs/{rfq['id']}/send-mail", headers=HEADERS)
    assert retry.status_code == 200 and len(sent) == 3
    client.post(f"/api/v1/rfqs/{rfq['id']}/send-mail", headers=HEADERS)
    assert len(sent) == 3
    with SessionLocal() as db:
        mails = list(db.scalars(select(RFQMail).where(RFQMail.rfq_id == rfq["id"])))
        assert all(m.status == "sent" for m in mails)
        settings = db.get(MailSettings, 1)
        settings.auto_send = False
        db.commit()
