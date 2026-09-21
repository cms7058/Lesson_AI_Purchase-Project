import json
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.persistence import DataConnectorRecord, StaffUserRecord
from app.domain.projects import ProjectBaseline, ProjectInput, ProjectRecord, project_data
from app.services.audit_service import write_audit_log
from app.services.project_access import project_access, roles

router = APIRouter(prefix='/projects', tags=['projects'], dependencies=[Depends(project_access)])


class TextImport(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class SchedulePreview(BaseModel):
    project_id: str = ''
    project: ProjectInput
    task_id: str
    days: int = Field(ge=-3650, le=3650)


@router.post('/schedule-preview')
def schedule_preview(payload: SchedulePreview, db=Depends(get_db), user=Depends(get_current_user)):
    if user.role not in ('admin', 'procurement_manager') and roles(db, user).get(payload.project_id) != 'planner':
        raise HTTPException(403, '无计划编辑权限')
    from app.services.project_schedule import shift_tasks
    if payload.project.status in ('completed', 'archived'):
        raise HTTPException(409, '已完成或归档项目不可拖动排期')
    return shift_tasks(payload.project.tasks, payload.task_id, payload.days)


def imported_preview(db, text, filename, notes=None):
    from app.services.project_text_import import preview
    result = preview(text, filename, notes)
    matches = db.scalars(select(ProjectRecord).where(ProjectRecord.payload.contains(result['fingerprint'])).limit(20))
    result['existing_projects'] = [{'id': p.id, 'code': p.code, 'name': p.name} for p in matches]
    return result


@router.post('/import-text')
def import_text(payload: TextImport, db=Depends(get_db)):
    return imported_preview(db, payload.text, '粘贴文本')


@router.post('/import-file')
async def import_file(file: UploadFile = File(...), db=Depends(get_db)):
    from app.services.project_text_import import extract
    filename = (file.filename or 'unknown').replace('\\', '/').split('/')[-1][:200]
    raw = await file.read(5*1024*1024+1)
    if filename.lower().endswith('.pdf'):
        if len(raw) > 5*1024*1024:
            raise HTTPException(422, '文件不能超过5MB')
        from app.services.mineru_client import MinerUError, extract_pdf
        connector = db.scalar(select(DataConnectorRecord).where(
            DataConnectorRecord.connector_type == 'mineru',
            DataConnectorRecord.status == 'active',
        ).order_by(DataConnectorRecord.created_at.desc()))
        try:
            text, engine = await extract_pdf(raw, filename, connector.base_url if connector else '')
            notes = [f'{engine}已提取PDF版式、表格和OCR文本；结果仅生成项目草稿，须对照原文复核。']
        except MinerUError as mineru_error:
            from app.services.project_text_import import extract_pdf_text
            text, local_engine = extract_pdf_text(raw)
            if len(text) < 10:
                raise HTTPException(422, str(mineru_error) + '；本地也未提取到文本，请配置并启用MinerU连接器') from None
            notes = [f'MinerU不可用，本次使用{local_engine}提取可检索文本；扫描内容、表格和版式可能缺失，请核查原文件。']
    else:
        text, notes = extract(raw, filename)
    if len(text) > 20000:
        text = text[:20000]
        notes.append('PDF正文超过20000字，本次仅使用前20000字生成项目草稿。')
    return imported_preview(db, text, filename, notes)


@router.get('/dashboard')
def dashboard(currency: str = 'CNY', status: str = '', manager_id: str = '', month: str = '', page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db=Depends(get_db)):
    all_rows = [project_data(r) for r in db.scalars(select(ProjectRecord).order_by(ProjectRecord.code))]
    currencies = sorted({r['currency'] for r in all_rows} | {'CNY'})
    rows = [r for r in all_rows if r['currency'] == currency and (not status or r['status'] == status) and (not manager_id or (r['manager_id'] or 'unassigned') == manager_id)]
    # Month denotes planned task finish, not project creation or accounting period.
    rows = [r for r in rows if not month or any((t.get('finish') or '').startswith(month) for t in r['tasks'])]
    staff = {s.id: s.name for s in db.scalars(select(StaffUserRecord))}
    statuses, managers, trend = Counter(), Counter(), Counter()
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    tasks = completed = overdue = 0
    for r in rows:
        statuses[r['status']] += 1
        managers[r['manager_id']] += 1
        for t in r['tasks']:
            if t['kind'] == 'work_package' or (month and not (t.get('finish') or '').startswith(month)):
                continue
            tasks += 1
            completed += t['progress'] == 100
            overdue += r['status'] == 'active' and bool(t.get('finish')) and t['finish'] < today and t['progress'] < 100
            if t.get('finish'):
                trend[t['finish'][:7]] += 1
    return {'currencies': currencies, 'project_count': len(rows), 'budget': sum(r['budget'] for r in rows), 'tasks': tasks, 'completed': completed, 'overdue': overdue,
            'statuses': [{'name': k, 'value': v, 'key': k} for k, v in statuses.items()],
            'managers': [{'name': staff.get(k, '未分配'), 'value': v, 'key': k or 'unassigned'} for k, v in managers.items()],
            'trend': [{'name': k, 'value': v} for k, v in sorted(trend.items())],
            'rows': [{**r, 'manager_name': staff.get(r['manager_id'], '未分配')} for r in rows[(page-1)*page_size:page*page_size]], 'total': len(rows)}


@router.post('/import-xml')
async def import_xml(file: UploadFile = File(...)):
    from app.services.project_import import xml_preview
    return xml_preview(await file.read(2 * 1024 * 1024 + 1))


def get_record(db, project_id):
    record = db.get(ProjectRecord, project_id)
    if not record:
        raise HTTPException(404, '项目不存在')
    return record


def validate_staff(db, data):
    for staff_id in {data.manager_id, *(t.owner_id for t in data.tasks)} - {None, ''}:
        staff = db.get(StaffUserRecord, staff_id)
        if not staff or staff.status != 'active':
            raise HTTPException(422, '负责人必须来自已启用的共享人员档案')


@router.get('')
def list_projects(keyword: str = '', status: str = '', page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db=Depends(get_db), user=Depends(get_current_user)):
    filters = []
    if user.role not in ('admin', 'procurement_manager'):
        filters.append(ProjectRecord.id.in_(list(roles(db, user))))
    if keyword:
        filters.append(or_(ProjectRecord.code.contains(keyword), ProjectRecord.name.contains(keyword)))
    if status:
        filters.append(ProjectRecord.status == status)
    total = db.scalar(select(func.count()).select_from(ProjectRecord).where(*filters))
    records = db.scalars(select(ProjectRecord).where(*filters).order_by(ProjectRecord.code).offset((page-1)*page_size).limit(page_size))
    return {'items': [project_data(r) for r in records], 'total': total, 'page': page, 'page_size': page_size}


@router.post('')
def create(data: ProjectInput, db=Depends(get_db), user=Depends(get_current_user)):
    validate_staff(db, data)
    record = ProjectRecord(code=data.code, name=data.name, status=data.status, payload=data.model_dump_json())
    db.add(record)
    try:
        db.flush()
        write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='create', resource_type='project', resource_id=record.id, detail='创建项目 '+data.code)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '项目编号重复') from None
    return project_data(record)


@router.get('/{project_id}')
def detail(project_id: str, db=Depends(get_db)):
    return project_data(get_record(db, project_id))


@router.put('/{project_id}')
def save(project_id: str, data: ProjectInput, db=Depends(get_db), user=Depends(get_current_user)):
    from app.domain.project_costs import ProjectAllocation
    record = get_record(db, project_id)
    if user.role not in ('admin', 'procurement_manager'):
        old = ProjectInput.model_validate(project_data(record)).model_dump(exclude={'tasks', 'version'})
        if old != data.model_dump(exclude={'tasks', 'version'}) or record.status in ('completed', 'archived'):
            raise HTTPException(403, '计划编辑权限只能调整任务，不能变更项目状态、预算及档案')
    allocations = list(db.scalars(select(ProjectAllocation).where(ProjectAllocation.project_id == project_id)))
    if allocations and (project_data(record)['currency'] != data.currency or any(a.task_id and a.task_id not in {t.id for t in data.tasks} for a in allocations)):
        raise HTTPException(409, '项目已有采购分摊，不可更改币种或移除关联任务')
    validate_staff(db, data)
    try:
        result = db.execute(update(ProjectRecord).where(ProjectRecord.id == project_id, ProjectRecord.version == data.version).values(code=data.code, name=data.name, status=data.status, payload=data.model_dump_json(), version=data.version+1))
        if not result.rowcount:
            raise HTTPException(409, '项目已被其他人修改，请重新加载后合并')
        write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='update', resource_type='project', resource_id=project_id, detail='更新项目 '+data.code)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '项目编号重复') from None
    return project_data(get_record(db, project_id))


@router.delete('/{project_id}', status_code=204)
def remove(project_id: str, version: int, db=Depends(get_db), user=Depends(get_current_user)):
    from app.domain.project_access import ProjectGrant
    if db.scalar(select(ProjectGrant.id).where(ProjectGrant.project_id == project_id).limit(1)):
        raise HTTPException(409, '项目存在人员授权，请先撤销授权')
    from app.domain.project_costs import ProjectAllocation
    if db.scalar(select(ProjectAllocation.id).where(ProjectAllocation.project_id == project_id).limit(1)):
        raise HTTPException(409, '项目已有采购分摊，请先解除关联')
    record = get_record(db, project_id)
    if record.version != version or record.status != 'draft':
        raise HTTPException(409, '只能删除未被修改的草稿；正式项目请归档')
    db.delete(record)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='delete', resource_type='project', resource_id=project_id, detail='删除项目草稿')
    db.commit()


@router.get('/{project_id}/alerts')
def alerts(project_id: str, db=Depends(get_db)):
    data = json.loads(get_record(db, project_id).payload)
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    items = []
    if data['status'] == 'active':
        for task in data['tasks']:
            if task['finish'] and task['finish'] < today and task['progress'] < 100:
                items.append({'task': task['name'], 'owner_id': task['owner_id'], 'type': '逾期', 'due': task['finish']})
    return {'items': items, 'note': '实时站内检查；尚未发送邮件'}


@router.post('/{project_id}/baselines')
def baseline(project_id: str, version: int, db=Depends(get_db), user=Depends(get_current_user)):
    record = get_record(db, project_id)
    if record.status != 'active' or version != record.version:
        raise HTTPException(409, '仅能为最新已发布计划建立基线，请保存并刷新后重试')
    row = ProjectBaseline(project_id=project_id, project_version=version, created_by=user.user_id,
                          created_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), payload=record.payload)
    db.add(row)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action='baseline', resource_type='project', resource_id=project_id, detail=f'确认计划基线 v{version}')
    db.commit()
    return {'id': row.id, 'project_version': row.project_version}


@router.get('/{project_id}/baselines')
def baselines(project_id: str, page: int = Query(1, ge=1), db=Depends(get_db)):
    current = project_data(get_record(db, project_id))
    query = select(ProjectBaseline).where(ProjectBaseline.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(ProjectBaseline).where(ProjectBaseline.project_id == project_id))
    rows = db.scalars(query.order_by(ProjectBaseline.created_at.desc()).offset((page-1)*10).limit(10))
    result = []
    for row in rows:
        previous = {t['id']: t for t in json.loads(row.payload)['tasks']}
        latest = {t['id']: t for t in current['tasks']}
        changes = []
        for key in previous.keys() | latest.keys():
            a, b = previous.get(key), latest.get(key)
            if not a or not b or a['start'] != b['start'] or a['finish'] != b['finish']:
                changes.append({'name': (b or a)['name'], 'change': '新增' if not a else '移除' if not b else '日期调整', 'before': [a['start'], a['finish']] if a else [], 'after': [b['start'], b['finish']] if b else []})
        result.append({'id': row.id, 'version': row.project_version, 'created_at': row.created_at, 'created_by': row.created_by, 'changes': changes})
    return {'items': result, 'total': total}
