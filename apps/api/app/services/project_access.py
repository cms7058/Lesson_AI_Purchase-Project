from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_, select

from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.persistence import StaffUserRecord
from app.domain.project_access import ProjectGrant


def roles(db, user):
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    staff = db.scalar(select(StaffUserRecord).where(or_(StaffUserRecord.id == user.user_id, StaffUserRecord.user_code == user.user_id), StaffUserRecord.status == 'active'))
    if not staff:
        return {}
    grants = db.scalars(select(ProjectGrant).where(ProjectGrant.staff_id == staff.id, ProjectGrant.valid_from <= today, ProjectGrant.valid_to >= today))
    result = {}
    for grant in grants:
        if result.get(grant.project_id) != 'planner':
            result[grant.project_id] = grant.role
    return result


def project_access(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    if user.role in ('admin', 'procurement_manager'):
        return
    project_id = request.path_params.get('project_id')
    if request.method == 'GET' and request.url.path.rstrip('/').endswith('/projects'):
        return
    if request.method == 'POST' and request.url.path.endswith('/schedule-preview'):
        return
    role = roles(db, user).get(project_id)
    if role and request.method == 'GET':
        return
    if role == 'planner' and request.method == 'PUT':
        return
    raise HTTPException(403, '没有当前项目操作权限或授权已失效')
