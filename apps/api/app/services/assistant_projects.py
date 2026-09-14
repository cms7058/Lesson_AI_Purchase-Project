"""Read-only project conversation grounded in authorized project snapshots."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.domain.projects import ProjectRecord
from app.domain.persistence import StaffUserRecord
from app.services.project_access import roles


def project_answer(db, payload, user):
    message = payload.message
    if payload.resource not in (None, 'projects'):
        return None
    if not any(w in message for w in ('项目', '任务', '甘特', '里程碑')) and any(w in message for w in ('订单', '询价', '物料', '供应商')):
        return None
    previous = [h.get('content', '') for h in payload.history if h.get('role') == 'user']
    context = ' '.join(previous[-3:] + [message])
    if payload.resource != 'projects' and not any(w in context for w in ('项目', '任务', '甘特', '里程碑')):
        return None
    query = select(ProjectRecord).order_by(ProjectRecord.code)
    if user.role not in ('admin', 'procurement_manager'):
        query = query.where(ProjectRecord.id.in_(list(roles(db, user))))
    records = list(db.scalars(query))
    named = [r for r in records if r.code.lower() in message.lower() or r.name in message]
    if not named and any(w in message for w in ('它', '这个', '其中', '继续', '这些')):
        named = [r for r in records if r.code.lower() in context.lower() or r.name in context]
    import re
    codes = re.findall(r'[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9-]+', message)
    records = named or ([r for r in records if any(c.lower() in r.code.lower() for c in codes)] if codes else records)
    for word, status in [('执行中', 'active'), ('草稿', 'draft'), ('已完成', 'completed'), ('归档', 'archived')]:
        if word in message and '任务' not in message:
            records = [r for r in records if r.status == status]
    staff = {s.id: s.name for s in db.scalars(select(StaffUserRecord))}
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    task_mode = any(w in message for w in ('任务', '逾期', '延期', '里程碑', '负责人', '跟踪'))
    rows = []
    for r in records:
        data = json.loads(r.payload)
        tasks = data.get('tasks', [])
        late = lambda t: bool(t.get('finish') and t['finish'] < today and t.get('progress', 0) < 100)
        if task_mode:
            for t in tasks:
                if any(w in message for w in ('逾期', '延期')) and not late(t):
                    continue
                if '里程碑' in message and t.get('kind') != 'milestone':
                    continue
                rows.append({'code': r.code, 'name': t['name'], 'owner': staff.get(t.get('owner_id'), '未分配'), 'start': t.get('start'), 'finish': t.get('finish'), 'progress': t.get('progress', 0), 'state': '已完成' if t.get('progress') == 100 else '逾期' if late(t) else '未逾期'})
        else:
            rows.append({'code': r.code, 'name': r.name, 'owner': staff.get(data.get('manager_id'), '未分配'), 'state': {'active':'执行中','draft':'草稿','completed':'已完成','archived':'归档'}.get(r.status,r.status), 'progress': round(sum(t.get('progress',0) for t in tasks)/len(tasks),1) if tasks else 0, 'overdue': sum(late(t) for t in tasks), 'budget':data.get('budget',0), 'currency':data.get('currency','CNY')})
    counts = {}
    for row in rows:
        counts[row['state']] = counts.get(row['state'], 0) + 1
    labels = {'code':'项目编号','name':'任务名称' if task_mode else '项目名称','owner':'负责人','start':'开始日期','finish':'结束日期','progress':'进度 %（任务均值）' if not task_mode else '进度 %','state':'状态','overdue':'逾期任务数','budget':'计划预算（非实际成本）','currency':'币种'}
    keys = ['code','name','owner','state','progress','start','finish'] if task_mode else ['code','name','owner','state','progress','overdue','budget','currency']
    result = {'resource':'projects','title':'项目任务' if task_mode else '项目','total':len(rows),'page':payload.page,'page_size':payload.page_size,'filters':[],'available_fields':[],'columns':[{'key':k,'label':labels[k]} for k in keys],'rows':rows[(payload.page-1)*payload.page_size:payload.page*payload.page_size],'chart':{'title':'任务状态分布' if task_mode else '项目状态分布','data':[{'name':k,'value':v} for k,v in counts.items()]}}
    text = f'在你的授权范围内找到 {len(rows)} 条{result["title"]}记录。' + '；'.join(f'{k} {v} 条' for k,v in counts.items())
    if any(w in message for w in ('建议','如何','分析','报告','跟踪')):
        text += '\n建议优先检查逾期任务的负责人和前置依赖，再确认交付时间；项目进度按任务进度简单平均，不代表工时加权完成率。预算按原币种展示，不跨币种合计。'
    if any(w in message for w in ('修改','删除','推迟','发送')):
        text += '\n本助手当前只读，未执行修改或发送；请在项目工作台确认操作。'
    return text, result
