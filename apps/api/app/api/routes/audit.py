from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.persistence import AuditLogRecord

router = APIRouter(prefix="/audit-logs", tags=["audit"])


class AuditLog(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: str
    actor_role: str
    action: str
    resource_type: str
    resource_id: str
    detail: str
    created_at: datetime


@router.get("", response_model=Page[AuditLog])
def list_audit_logs(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = Query("", max_length=100), resource_type: str = Query("", max_length=50), db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)
) -> Page[AuditLog]:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.AUDITOR}:
        return Page(items=[], page=page, page_size=page_size, total=0)
    statement = select(AuditLogRecord)
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(or_(AuditLogRecord.detail.ilike(pattern), AuditLogRecord.actor_id.ilike(pattern), AuditLogRecord.resource_id.ilike(pattern)))
    if resource_type:
        statement = statement.where(AuditLogRecord.resource_type == resource_type)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    records = db.scalars(statement.order_by(AuditLogRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return Page(items=list(records), page=page, page_size=page_size, total=total)
