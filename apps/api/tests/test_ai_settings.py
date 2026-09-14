from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"X-User-Role": "procurement_manager", "X-User-Id": "ai-settings-test"}


def test_ai_settings_key_is_never_returned(monkeypatch):
    monkeypatch.setenv("PEBS_SECRET_KEY", Fernet.generate_key().decode())
    response = client.put("/api/v1/ai-model-settings", headers=HEADERS, json={"enabled": True, "provider": "openai_compatible", "base_url": "https://vision.example/v1/", "model": "vision-test", "api_key": "top-secret"})
    assert response.status_code == 200, response.text
    assert response.json()["api_key_set"] is True
    assert "api_key" not in response.json()
    read = client.get("/api/v1/ai-model-settings", headers=HEADERS)
    assert read.json()["base_url"] == "https://vision.example/v1"
    assert "top-secret" not in read.text


def test_ai_settings_rejects_incomplete_enabled_configuration():
    response = client.put("/api/v1/ai-model-settings", headers=HEADERS, json={"enabled": True, "provider": "openai_compatible", "base_url": "", "model": ""})
    assert response.status_code == 422
