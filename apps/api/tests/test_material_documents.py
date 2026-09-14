from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
MANAGER = {"X-User-Id": "manager-tech-doc", "X-User-Role": "procurement_manager"}
BUYER = {"X-User-Id": "buyer-tech-doc", "X-User-Role": "buyer"}


def material() -> dict:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/v1/materials",
        headers=MANAGER,
        json={"code": f"TECH-{suffix}", "name": "伺服驱动器", "specification": "750W/220V", "category": "电气", "unit": "件"},
    )
    assert response.status_code == 201
    return response.json()


def upload(material_id: str, version: str, *, document_no: str = "DWG-TECH-001", headers: dict = MANAGER) -> dict:
    response = client.post(
        f"/api/v1/materials/{material_id}/technical-documents",
        headers=headers,
        data={"document_no": document_no, "title": "伺服驱动器安装图", "document_type": "drawing", "version": version, "effective_date": "2026-09-13", "description": "采购及到货验收依据"},
        files={"file": (f"驱动器图纸-{version}.pdf", b"%PDF-1.4\n% controlled demo drawing\n%%EOF", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def approve(document_id: str) -> dict:
    assert client.post(f"/api/v1/material-technical-documents/{document_id}/submit", headers=BUYER).status_code == 200
    response = client.post(f"/api/v1/material-technical-documents/{document_id}/decision", headers=MANAGER, json={"approved": True, "note": "技术与质量会签通过"})
    assert response.status_code == 200
    return response.json()


def test_material_document_version_approval_and_obsolete_loop() -> None:
    item = material()
    first = upload(item["id"], "A")
    assert first["status"] == "draft"
    duplicate = client.post(
        f"/api/v1/materials/{item['id']}/technical-documents",
        headers=MANAGER,
        data={"document_no": "DWG-TECH-001", "title": "重复版本", "document_type": "drawing", "version": "A"},
        files={"file": ("duplicate.pdf", b"%PDF-1.4 duplicate", "application/pdf")},
    )
    assert duplicate.status_code == 409
    assert client.patch(f"/api/v1/material-technical-documents/{first['id']}", headers=BUYER, json={"title": "伺服驱动器安装与验收图"}).status_code == 200
    assert approve(first["id"])["status"] == "active"
    assert client.patch(f"/api/v1/material-technical-documents/{first['id']}", headers=MANAGER, json={"title": "不能修改"}).status_code == 409
    assert client.delete(f"/api/v1/material-technical-documents/{first['id']}", headers=MANAGER).status_code == 409

    second = upload(item["id"], "B")
    assert client.post(f"/api/v1/material-technical-documents/{second['id']}/submit", headers=BUYER).status_code == 200
    assert client.post(f"/api/v1/material-technical-documents/{second['id']}/decision", headers=BUYER, json={"approved": True, "note": ""}).status_code == 403
    assert client.post(f"/api/v1/material-technical-documents/{second['id']}/decision", headers=MANAGER, json={"approved": True, "note": "B版替代A版"}).json()["status"] == "active"

    listed = client.get(f"/api/v1/materials/{item['id']}/technical-documents?page=1&page_size=10").json()
    by_version = {row["version"]: row for row in listed["items"]}
    assert by_version["A"]["status"] == "obsolete"
    assert by_version["B"]["status"] == "active"
    assert listed["counts"]["active"] == 1
    assert listed["counts"]["obsolete"] == 1
    assert client.get(f"/api/v1/material-technical-documents/{second['id']}/download").content.startswith(b"%PDF")
    history = client.get(f"/api/v1/material-technical-documents/{second['id']}/history?page=1&page_size=20").json()
    assert history["total"] == 3
    assert {row["action"] for row in history["items"]} == {"create", "submit", "approve"}
    assert client.delete(f"/api/v1/materials/{item['id']}", headers=MANAGER).status_code == 409


def test_material_document_validation_rejection_and_draft_delete() -> None:
    item = material()
    denied = client.post(
        f"/api/v1/materials/{item['id']}/technical-documents",
        headers={"X-User-Role": "analyst"},
        data={"document_no": "SPEC-1", "title": "技术规格", "document_type": "specification", "version": "1.0"},
        files={"file": ("spec.exe", b"unsafe", "application/octet-stream")},
    )
    assert denied.status_code == 403
    invalid = client.post(
        f"/api/v1/materials/{item['id']}/technical-documents",
        headers=MANAGER,
        data={"document_no": "SPEC-1", "title": "技术规格", "document_type": "specification", "version": "1.0"},
        files={"file": ("spec.exe", b"unsafe", "application/octet-stream")},
    )
    assert invalid.status_code == 422
    doc = upload(item["id"], "1.0", document_no="SPEC-1")
    client.post(f"/api/v1/material-technical-documents/{doc['id']}/submit", headers=BUYER)
    rejected = client.post(f"/api/v1/material-technical-documents/{doc['id']}/decision", headers=MANAGER, json={"approved": False, "note": "请补充公差要求"})
    assert rejected.json()["status"] == "draft"
    assert rejected.json()["review_note"] == "请补充公差要求"
    assert client.delete(f"/api/v1/material-technical-documents/{doc['id']}", headers=BUYER).status_code == 204
