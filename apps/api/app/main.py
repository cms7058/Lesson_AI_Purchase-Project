from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import app.domain.persistence
from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import Base, engine

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI助力智能项目与采购教学体验平台 API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_prefix)
app.mount("/files/documents", StaticFiles(directory="generated_documents"), name="documents")
app.mount("/files/assets", StaticFiles(directory="generated_assets"), name="assets")
# Development bootstrap. Production deployment replaces this with Alembic migrations.
if settings.auto_create_schema:
    Base.metadata.create_all(bind=engine)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
