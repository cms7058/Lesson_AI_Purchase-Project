from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.company import CompanyProfile, CompanyProfileUpdate
from app.domain.persistence import CompanyProfileRecord
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/company-profile", tags=["company-profile"])
ASSET_DIR = Path("generated_assets")
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg"}


def get_profile(db: Session) -> CompanyProfileRecord:
    profile = db.get(CompanyProfileRecord, 1)
    if profile is None:
        profile = CompanyProfileRecord(id=1)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.get("", response_model=CompanyProfile)
def read_profile(db: Session = Depends(get_db)) -> CompanyProfileRecord:
    return get_profile(db)


@router.put("", response_model=CompanyProfile)
def update_profile(payload: CompanyProfileUpdate, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> CompanyProfileRecord:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权修改公司标识")
    profile = get_profile(db)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="update", resource_type="company_profile", resource_id="1", detail="更新公司标识")
    db.commit(); db.refresh(profile)
    return profile


@router.post("/logo", response_model=CompanyProfile)
def upload_logo(logo: UploadFile = File(...), db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> CompanyProfileRecord:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权上传Logo")
    if logo.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="仅支持PNG或JPEG格式Logo")
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".png" if logo.content_type == "image/png" else ".jpg"
    filename = f"company-logo-{uuid4().hex}{suffix}"
    output = ASSET_DIR / filename
    output.write_bytes(logo.file.read())
    profile = get_profile(db)
    profile.logo_path = f"/files/assets/{filename}"
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="upload", resource_type="company_profile", resource_id="1", detail="上传公司Logo")
    db.commit(); db.refresh(profile)
    return profile
