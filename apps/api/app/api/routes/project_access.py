from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.security import UserRole, get_current_user, require_roles
from app.domain.persistence import StaffUserRecord
from app.domain.project_access import GrantInput, ProjectGrant
from app.domain.projects import ProjectRecord
from app.services.audit_service import write_audit_log

router = APIRouter(prefix='/project-grants', tags=['project-grants'], dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER))])


@router.get('')
def listing(project_id: str = '', staff_id: str = '', page: int = Query(1, ge=1), db=Depends(get_db)):
    filters = []
    if project_id:
        filters.append(ProjectGrant.project_id == project_id)
    if staff_id:
        filters.append(ProjectGrant.staff_id == staff_id)
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    items = []
    for g in db.scalars(select(ProjectGrant).where(*filters).order_by(ProjectGrant.id).offset((page-1)*10).limit(10)):
        s, p = db.get(StaffUserRecord, g.staff_id), db.get(ProjectRecord, g.project_id)
        items.append({'id': g.id, 'project_id': g.project_id, 'staff_id': g.staff_id, 'project': p.name if p else '已删除项目', 'staff': s.name if s else '已删除人员', 'role': g.role, 'valid_from': g.valid_from, 'valid_to': g.valid_to, 'effective': bool(s and s.status == 'active' and p and g.valid_from <= today <= g.valid_to)})
    return {'items': items, 'total': db.scalar(select(func.count()).select_from(ProjectGrant).where(*filters))}


def persist(db, data, user, item=None):
    if not db.get(ProjectRecord, data.project_id) or not db.get(StaffUserRecord, data.staff_id):
        raise HTTPException(422, '项目或人员不存在')
    duplicate = db.scalar(select(ProjectGrant).where(ProjectGrant.project_id == data.project_id, ProjectGrant.staff_id == data.staff_id, ProjectGrant.id != (item.id if item else ''), ProjectGrant.valid_from <= data.valid_to, ProjectGrant.valid_to >= data.valid_from))
    if duplicate:
        raise HTTPException(409, '此人员在该项目已有重叠有效期授权，请编辑原授权')
    item = item or ProjectGrant()
    for k, v in data.model_dump().items():
        setattr(item, k, v)
    db.add(item)
    db.flush()
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='grant', resource_type='project_grant', resource_id=item.id, detail=f'项目{data.project_id}人员{data.staff_id}角色{data.role}')
    db.commit()
    return {'id': item.id}


@router.post('')
def create(data: GrantInput, db=Depends(get_db), user=Depends(get_current_user)):
    return persist(db, data, user)


@router.put('/{item_id}')
def edit(item_id: str, data: GrantInput, db=Depends(get_db), user=Depends(get_current_user)):
    item = db.get(ProjectGrant, item_id)
    if not item:
        raise HTTPException(404, '授权不存在')
    return persist(db, data, user, item)


@router.delete('/{item_id}', status_code=204)
def remove(item_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    item = db.get(ProjectGrant, item_id)
    if not item:
        raise HTTPException(404, '授权不存在')
    db.delete(item)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='revoke', resource_type='project_grant', resource_id=item_id, detail='撤销项目授权')
    db.commit()
