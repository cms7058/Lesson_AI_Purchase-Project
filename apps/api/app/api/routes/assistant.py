from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.routes.ai_settings import effective_ai_config
from app.api.routes.supplier_portal import supplier_user
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.domain.persistence import SupplierRecord
from app.services.assistant_service import AssistantRequest, AssistantResponse, respond

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat", response_model=AssistantResponse)
def chat(
    payload: AssistantRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    authorization: str = Header(""),
) -> AssistantResponse:
    supplier = None
    if authorization:
        account = supplier_user(authorization, db)
        supplier = db.get(SupplierRecord, account.supplier_id)
    domain = "project" if ("project" in (payload.context_module or "") or payload.resource == "projects" or "项目" in payload.message) else "procurement"
    return respond(payload, settings, db, "supplier" if supplier else user.role, supplier, user=user, ai_config=effective_ai_config(db, domain))
