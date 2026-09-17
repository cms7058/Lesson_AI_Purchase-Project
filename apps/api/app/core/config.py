from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    auto_create_schema: bool = True
    app_name: str = "AI助力"
    api_prefix: str = "/api/v1"
    web_origins: str = "http://localhost:8080"
    database_url: str = "sqlite:///./pebs_purchase.db"
    redis_url: str = "redis://localhost:6379/0"
    llm_provider: str = "disabled"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    mineru_base_url: str = ""
    mineru_api_key: str = ""
    mineru_backend: str = "pipeline"
    mineru_timeout_seconds: int = 120
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    system_admin_username: str = "admin"
    system_admin_password: str = "admin123456"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [value.strip() for value in self.web_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
