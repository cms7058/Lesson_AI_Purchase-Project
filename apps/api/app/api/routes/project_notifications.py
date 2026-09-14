from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.security import UserRole, get_current_user, require_roles
from app.domain.project_notifications import ProjectNotification
from app.services.audit_service import write_audit_log
from app.services.project_notifications import scan, send

router = APIRouter(prefix='/project-notifications', tags=['project-notifications'], dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER))])


@router.get('')
def listing(state: str = '', page: int = Query(1, ge=1), db=Depends(get_db)):
    filters = [ProjectNotification.state == state] if state else []
    rows = db.scalars(select(ProjectNotification).where(*filters).order_by(ProjectNotification.created_at.desc()).offset((page-1)*10).limit(10))
    return {'items': [{k: getattr(r, k) for k in ('id', 'project_id', 'subject', 'body', 'state', 'mail_status', 'recipient', 'error', 'created_at')} for r in rows], 'total': db.scalar(select(func.count()).select_from(ProjectNotification).where(*filters))}


@router.post('/scan')
def refresh(db=Depends(get_db), user=Depends(get_current_user)):
    n = scan(db)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='scan', resource_type='project_notification', resource_id='all', detail=f'扫描任务节点，新增{n}条提醒')
    db.commit()
    return {'inserted': n}


@router.post('/{item_id}/acknowledge')
def acknowledge(item_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    item = db.get(ProjectNotification, item_id)
    if not item or item.state != 'open':
        raise HTTPException(409, '提醒不存在或不在待处理状态')
    item.state = 'acknowledged'
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='acknowledge', resource_type='project_notification', resource_id=item_id, detail='确认收到项目提醒')
    db.commit()
    return {'state': item.state}


@router.post('/{item_id}/send')
def dispatch(item_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    scan(db)
    db.commit()
    result = send(db, item_id)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='send', resource_type='project_notification', resource_id=item_id, detail='邮件结果：'+result['mail_status'])
    db.commit()
    return result
