from fastapi import APIRouter

from app.domain.catalog import MODULES, ModuleDefinition

router = APIRouter(tags=["catalog"])


@router.get("/modules", response_model=list[ModuleDefinition])
def list_modules() -> list[ModuleDefinition]:
    return MODULES

