import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import CurrentUser, get_system_user
from app.domain.persistence import StaffUserRecord
from app.domain.teaching import LearningAccountRecord, SystemSessionRecord

router = APIRouter(prefix="/auth", tags=["system-auth"])


class LoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _verify_learning_password(password: str, encoded: str) -> bool:
    try:
        salt, _ = encoded.split(":", 1)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
        return hmac.compare_digest(encoded, f"{salt}:{digest}")
    except Exception:
        return False


def _session_out(row: SystemSessionRecord) -> dict:
    return {
        "user_id": row.user_id,
        "username": row.username,
        "name": row.display_name,
        "role": row.role,
        "organization": "AI助力教学平台",
    }


@router.post("/login")
def login(payload: LoginInput, db: Session = Depends(get_db)):
    settings = get_settings()
    user_id = ""
    role = ""
    display_name = ""

    admin_name_ok = hmac.compare_digest(payload.username, settings.system_admin_username)
    admin_password_ok = hmac.compare_digest(payload.password, settings.system_admin_password)
    if admin_name_ok and admin_password_ok:
        user_id, role, display_name = "system-admin", "admin", "系统管理员"
    else:
        account = db.scalar(select(LearningAccountRecord).where(LearningAccountRecord.username == payload.username))
        staff = db.get(StaffUserRecord, account.staff_id) if account else None
        valid = (
            account
            and account.active
            and staff
            and staff.status == "active"
            and staff.role == "student"
            and (not account.locked_until or account.locked_until <= _now())
            and _verify_learning_password(payload.password, account.password_hash)
        )
        if not valid:
            if account:
                account.failures += 1
                if account.failures >= 5:
                    account.locked_until = _now() + timedelta(minutes=15)
                db.commit()
            raise HTTPException(401, "用户名或密码错误，或账号无系统登录权限")
        account.failures = 0
        account.locked_until = None
        account.last_login_at = _now()
        user_id, role, display_name = staff.id, "student", staff.name

    token = secrets.token_urlsafe(40)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db.add(
        SystemSessionRecord(
            token_hash=token_hash,
            user_id=user_id,
            username=payload.username,
            role=role,
            display_name=display_name,
            expires_at=_now() + timedelta(hours=12),
        )
    )
    db.commit()
    session = db.get(SystemSessionRecord, token_hash)
    return {"token": token, "user": _session_out(session)}


@router.get("/me")
def me(user: CurrentUser = Depends(get_system_user)):
    return {
        "user_id": user.user_id,
        "username": user.username,
        "name": user.name or "系统用户",
        "role": user.role,
        "organization": "AI助力教学平台",
    }


@router.post("/logout")
def logout(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    token = authorization.removeprefix("Bearer ").strip()
    if token:
        db.execute(delete(SystemSessionRecord).where(SystemSessionRecord.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        db.commit()
    return {"ok": True}
