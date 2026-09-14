from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, Header, HTTPException, status


class UserRole(StrEnum):
    ADMIN = "admin"
    PROCUREMENT_MANAGER = "procurement_manager"
    BUYER = "buyer"
    ANALYST = "analyst"
    AUDITOR = "auditor"


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    role: UserRole


def get_current_user(
    x_user_id: str = Header(default="demo-buyer"),
    x_user_role: UserRole = Header(default=UserRole.BUYER),
) -> CurrentUser:
    return CurrentUser(user_id=x_user_id, role=x_user_role)


def require_roles(*allowed_roles: UserRole):
    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前角色无权执行此操作",
            )
        return current_user

    return dependency
