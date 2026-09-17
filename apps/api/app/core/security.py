from dataclasses import dataclass
import hashlib
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.teaching import SystemSessionRecord


class UserRole(StrEnum):
    ADMIN = "admin"
    PROCUREMENT_MANAGER = "procurement_manager"
    BUYER = "buyer"
    ANALYST = "analyst"
    AUDITOR = "auditor"
    INSTRUCTOR = "instructor"
    STUDENT = "student"


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    role: UserRole
    username: str = ""
    name: str = ""


def get_current_user(
    authorization: str = Header(default=""),
    x_user_id: str = Header(default="demo-buyer"),
    x_user_role: UserRole = Header(default=UserRole.BUYER),
    db: Session = Depends(get_db),
) -> CurrentUser:
    token = authorization.removeprefix("Bearer ").strip()
    if token:
        session = db.get(SystemSessionRecord, hashlib.sha256(token.encode()).hexdigest())
        now = datetime.now(UTC).replace(tzinfo=None)
        if session and session.expires_at > now:
            return CurrentUser(
                user_id=session.user_id,
                role=UserRole(session.role),
                username=session.username,
                name=session.display_name,
            )
    return CurrentUser(user_id=x_user_id, role=x_user_role)


def get_system_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> CurrentUser:
    token = authorization.removeprefix("Bearer ").strip()
    session = db.get(SystemSessionRecord, hashlib.sha256(token.encode()).hexdigest()) if token else None
    now = datetime.now(UTC).replace(tzinfo=None)
    if not session or session.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="系统登录已过期，请重新登录")
    return CurrentUser(
        user_id=session.user_id,
        role=UserRole(session.role),
        username=session.username,
        name=session.display_name,
    )


def require_roles(*allowed_roles: UserRole):
    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前角色无权执行此操作",
            )
        return current_user

    return dependency
