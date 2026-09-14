from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"X-User-Role": "procurement_manager", "X-User-Id": "knowledge-test"}


def test_knowledge_crud_upload_and_assistant_retrieval():
    marker = uuid4().hex[:8]
    title = f"轴承紧急采购规则-{marker}"
    payload = {
        "title": title,
        "domain": "procurement",
        "document_type": "policy",
        "source_name": "测试制度",
        "tags": "轴承,紧急采购",
        "content": f"轴承紧急采购必须校验停机等级与最高溢价。检索标识{marker}。",
        "status": "active",
    }
    created = client.post("/api/v1/knowledge", json=payload, headers=HEADERS)
    assert created.status_code == 200, created.text
    row = created.json()
    listed = client.get("/api/v1/knowledge", params={"keyword": marker}, headers=HEADERS)
    assert listed.status_code == 200 and listed.json()["total"] == 1
    answer = client.post(
        "/api/v1/assistant/chat",
        json={"message": f"解释轴承紧急采购检索标识{marker}"},
        headers=HEADERS,
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["citations"][0]["title"] == title
    payload.update({"status": "archived", "version": row["version"]})
    updated = client.put(f"/api/v1/knowledge/{row['id']}", json=payload, headers=HEADERS)
    assert updated.status_code == 200 and updated.json()["version"] == 2
    deleted = client.delete(
        f"/api/v1/knowledge/{row['id']}",
        params={"version": 2},
        headers=HEADERS,
    )
    assert deleted.status_code == 200

    uploaded = client.post(
        "/api/v1/knowledge/upload",
        data={"title": f"项目复盘-{marker}", "domain": "project", "document_type": "case", "tags": "复盘"},
        files={"file": (f"review-{marker}.txt", f"项目延期复盘要求记录基线偏差、责任人和纠偏动作。{marker}".encode())},
        headers=HEADERS,
    )
    assert uploaded.status_code == 200, uploaded.text
    upload_row = uploaded.json()
    client.delete(f"/api/v1/knowledge/{upload_row['id']}", params={"version": upload_row["version"]}, headers=HEADERS)


def test_knowledge_write_permission():
    response = client.post(
        "/api/v1/knowledge",
        json={"title": "权限测试知识", "content": "普通采购员不能维护知识库正文。", "domain": "shared"},
        headers={"X-User-Role": "buyer", "X-User-Id": "buyer"},
    )
    assert response.status_code == 403


def test_ai_model_profiles_are_separated():
    procurement = client.put(
        "/api/v1/ai-model-settings",
        params={"domain": "procurement"},
        json={"enabled": False, "provider": "openai_compatible", "base_url": "", "model": "procurement-specialist"},
        headers=HEADERS,
    )
    project = client.put(
        "/api/v1/ai-model-settings",
        params={"domain": "project"},
        json={"enabled": False, "provider": "openai_compatible", "base_url": "", "model": "project-specialist"},
        headers=HEADERS,
    )
    assert procurement.status_code == 200 and project.status_code == 200
    assert client.get("/api/v1/ai-model-settings", params={"domain": "procurement"}, headers=HEADERS).json()["model"] == "procurement-specialist"
    assert client.get("/api/v1/ai-model-settings", params={"domain": "project"}, headers=HEADERS).json()["model"] == "project-specialist"
