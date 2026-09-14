import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.knowledge import AIModelProfileRecord
from app.domain.supplier_portal import AIModelSettings
from app.services.audit_service import write_audit_log
from app.services.rfq_mail import cipher

router = APIRouter(prefix="/ai-model-settings", tags=["ai-model-settings"])


def manager(user: CurrentUser = Depends(get_current_user)):
    if user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(403, "需要采购经理权限")
    return user


class AISettingsInput(BaseModel):
    enabled: bool = False
    provider: str = Field(default="openai_compatible", pattern="^openai_compatible$")
    base_url: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, max_length=2000)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        value = value.rstrip("/")
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("模型地址必须以http://或https://开头")
        return value


def effective_ai_config(db: Session, domain: str | None = None) -> dict:
    if domain:
        profile = db.get(AIModelProfileRecord, domain)
        if profile:
            try:
                key = cipher().decrypt(profile.api_key_encrypted.encode()).decode() if profile.api_key_encrypted else ""
            except InvalidToken:
                key = ""
            return {"enabled": profile.enabled, "provider": profile.provider, "base_url": profile.base_url, "model": profile.model, "api_key": key}
        if domain == "project":
            return {"enabled": False, "provider": "openai_compatible", "base_url": "", "model": "", "api_key": ""}
        settings = get_settings()
        provider = settings.llm_provider if settings.llm_provider != "disabled" else "openai_compatible"
        return {"enabled": settings.llm_provider != "disabled", "provider": provider, "base_url": settings.llm_base_url, "model": settings.llm_model, "api_key": settings.llm_api_key}
    item = db.get(AIModelSettings, 1)
    if item:
        try:
            key = cipher().decrypt(item.api_key_encrypted.encode()).decode() if item.api_key_encrypted else ""
        except InvalidToken:
            key = ""
        return {"enabled": item.enabled, "provider": item.provider, "base_url": item.base_url, "model": item.model, "api_key": key}
    settings = get_settings()
    provider = settings.llm_provider if settings.llm_provider != "disabled" else "openai_compatible"
    return {"enabled": settings.llm_provider != "disabled", "provider": provider, "base_url": settings.llm_base_url, "model": settings.llm_model, "api_key": settings.llm_api_key}


@router.get("", dependencies=[Depends(manager)])
def read_settings(domain: str | None = None, db: Session = Depends(get_db)):
    if domain is not None and domain not in {"procurement", "project"}:
        raise HTTPException(422, "模型域仅支持procurement或project")
    config = effective_ai_config(db, domain)
    return {k: v for k, v in config.items() if k != "api_key"} | {"api_key_set": bool(config["api_key"])}


@router.put("", dependencies=[Depends(manager)])
def save_settings(payload: AISettingsInput, domain: str | None = None, db: Session = Depends(get_db), user=Depends(manager)):
    if domain is not None and domain not in {"procurement", "project"}:
        raise HTTPException(422, "模型域仅支持procurement或project")
    item = (db.get(AIModelProfileRecord, domain) or AIModelProfileRecord(domain=domain)) if domain else (db.get(AIModelSettings, 1) or AIModelSettings(id=1))
    if payload.enabled and (not payload.base_url or not payload.model or (not payload.api_key and not item.api_key_encrypted)):
        raise HTTPException(422, "启用模型前必须填写模型地址、模型名称和API密钥")
    item.enabled, item.provider, item.base_url, item.model = payload.enabled, payload.provider, payload.base_url, payload.model
    if payload.api_key:
        item.api_key_encrypted = cipher().encrypt(payload.api_key.encode()).decode()
    db.add(item)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="update", resource_type="ai_model_settings", resource_id="1", detail="更新AI模型配置（不记录密钥）")
    db.commit()
    return read_settings(domain, db)


@router.post("/test", dependencies=[Depends(manager)])
def test_settings(domain: str | None = None, db: Session = Depends(get_db)):
    config = effective_ai_config(db, domain)
    if not all((config["enabled"], config["base_url"], config["model"], config["api_key"])):
        raise HTTPException(409, "请先保存并启用完整的AI模型配置")
    try:
        response = httpx.post(config["base_url"].rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {config['api_key']}"},
            json={"model": config["model"], "temperature": 0, "max_tokens": 10, "messages": [{"role": "user", "content": "仅回复OK"}]}, timeout=20)
        response.raise_for_status()
        answer = str(response.json()["choices"][0]["message"]["content"]).strip()
    except Exception as exc:
        raise HTTPException(502, "连接测试失败，请检查地址、密钥、模型权限与网络") from exc
    return {"ok": True, "message": answer[:80] or "OK", "model": config["model"]}
