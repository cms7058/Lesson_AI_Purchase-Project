from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import engine

router = APIRouter(tags=["system"])


@router.get('/ready')
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {'status': 'ready'}
    except SQLAlchemyError:
        raise HTTPException(503, 'Database unavailable') from None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-assist-teaching-api", "version": "0.1.0"}
