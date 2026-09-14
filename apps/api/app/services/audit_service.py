from sqlalchemy.orm import Session

from app.domain.persistence import AuditLogRecord


def write_audit_log(
    db: Session,
    *,
    actor_id: str,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: str = "",
) -> None:
    db.add(
        AuditLogRecord(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
        )
    )
