"""Additive, idempotent project demo fixtures; never dispatch mail or overwrite rows."""
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.domain.persistence import (
    AuditLogRecord,
    FactoryRecord,
    MaterialRecord,
    PurchaseOrderLineRecord,
    PurchaseOrderRecord,
    StaffUserRecord,
    SupplierRecord,
)
from app.domain.project_costs import ProjectAllocation
from app.domain.project_notifications import ProjectNotification
from app.domain.projects import ProjectBaseline, ProjectInput, ProjectRecord, ProjectTask

PREFIX = 'pebs-project-demo-v1:'


def uid(key):
    return str(uuid5(NAMESPACE_URL, PREFIX+key))


def seed(db):
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    today = now.date()
    counts = {}

    def put(model, key, **values):
        item = db.get(model, uid(key))
        if item:
            return item
        item = model(id=uid(key), **values)
        db.add(item)
        db.flush()
        counts[model.__tablename__] = counts.get(model.__tablename__, 0)+1
        return item

    staff = [put(StaffUserRecord, 'staff'+str(i), user_code=f'DEMO-PM-{i+1:02}', name='【演示】'+name, department='项目管理部', title='项目经理', role='procurement_manager', email='', created_by='project-demo') for i, name in enumerate(['陈晨', '李明', '王敏'])]
    supplier = put(SupplierRecord, 'supplier', code='DEMO-PROJECT-S01', name='【演示】精工设备配套厂')
    material = put(MaterialRecord, 'material', code='DEMO-PROJECT-M01', name='【演示】装配线控制组件')
    put(FactoryRecord, 'factory', code='DEMO-PROJECT-FACTORY', name='【演示】项目交付工厂')
    names = ['自动装配线交付', '汽车零件试制', '产线搬迁改造', '智能仓储规划', '工装夹具验收', '历史设备升级']
    statuses = ['active', 'active', 'active', 'draft', 'completed', 'archived']
    for i, name in enumerate(names):
        key = 'project'+str(i)
        # Once created, the entire project scenario belongs to the user.
        if db.get(ProjectRecord, uid(key)):
            continue
        manager = staff[i % len(staff)]
        tasks = []
        previous = None
        for j, title in enumerate(['需求确认', '方案设计', '采购准备', '设备到货', '安装调试', '最终验收']):
            start = today+timedelta(days=-35+j*10+i*6)
            finish = start+timedelta(days=7)
            progress = 100 if statuses[i] in ('completed', 'archived') or j<2 else 60 if j==2 else 0
            if j == 5:
                start = finish
            task = ProjectTask(id=f'T{j+1}', name='【演示】'+title, kind='milestone' if j==5 else 'task', owner_id=manager.id, start=start, finish=finish, progress=progress, predecessors=[previous] if previous else [])
            tasks.append(task)
            previous = task.id
        # A near-due task and an overdue task are intentional, not actual exceptions.
        if i == 0:
            tasks[2].finish = today-timedelta(days=1)
            tasks[3].start = today
            tasks[3].finish = today+timedelta(days=2)
        budget = [100000, 180000, 120000, 80000, 150000, 90000][i]
        data = ProjectInput(code=f'DEMO-PRJ-{i+1:03}', name='【演示】'+name, manager_id=manager.id, status=statuses[i], budget=budget, tasks=tasks, description='【演示数据】虚构项目，用于查看甘特图、负责人联动、采购分摊、基线及通知。不是实际业务。')
        project = put(ProjectRecord, key, code=data.code, name=data.name, status=data.status, payload=data.model_dump_json())
        baseline = data.model_copy(deep=True)
        if i == 0:
            baseline.tasks[3].start -= timedelta(days=5)
            baseline.tasks[3].finish -= timedelta(days=5)
        put(ProjectBaseline, 'baseline'+str(i), project_id=project.id, project_version=1, created_by='project-demo', created_at=(now-timedelta(days=10)).isoformat(), payload=baseline.model_dump_json())
        if i < 3:
            order = put(PurchaseOrderRecord, 'order'+str(i), order_no=f'DEMO-PJ-PO-{i+1:03}', supplier_id=supplier.id, supplier_name=supplier.name, factory_code='DEMO-PROJECT-FACTORY', currency='CNY', status='approved' if i<2 else 'draft', created_by='project-demo')
            line = db.scalar(select(PurchaseOrderLineRecord).where(PurchaseOrderLineRecord.order_id == order.id))
            if not line:
                line = PurchaseOrderLineRecord(order_id=order.id, material_code=material.code, material_name=material.name, quantity=Decimal(100), unit='件', unit_price=Decimal(1500 if i==0 else 800), tax_rate=Decimal('.13'))
                db.add(line)
                db.flush()
                counts['purchase_order_lines'] = counts.get('purchase_order_lines', 0)+1
            put(ProjectAllocation, 'allocation'+str(i), project_id=project.id, task_id='T3', line_id=line.id, order_id=order.id, quantity=Decimal(80))
        if i == 0:
            put(ProjectNotification, 'notice-cost', event_key=hashlib.sha256(f'cost|{project.id}|{manager.id}|{data.budget}|135600.00'.encode()).hexdigest(), project_id=project.id, task_id='', owner_id=manager.id, subject='【演示】采购承诺超预算 · '+data.code, body='【演示】采购承诺135600元，项目预算100000元，超出35600元。仅为演示，不代表实际支出。', kind='cost_overrun', created_at=now.isoformat())
            put(ProjectNotification, 'notice-task', event_key=hashlib.sha256(f'{project.id}|T3|{tasks[2].finish}|{manager.id}|overdue'.encode()).hexdigest(), project_id=project.id, task_id='T3', owner_id=manager.id, subject='【演示】采购准备逾期 · '+data.code, body='【演示】采购准备任务尚未完成，请在项目工作台查看计划。演示人员无邮箱，不发送邮件。', kind='overdue', created_at=now.isoformat())
    if counts:
        db.add(AuditLogRecord(actor_id='project-demo', actor_role='admin', action='seed_demo', resource_type='project_demo', resource_id='v1', detail='新增明确标记的虚构项目演示数据；不覆盖现有数据；不发送邮件。'))
    db.flush()
    return counts


if __name__ == '__main__':
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        result = seed(db)
    print(json.dumps({'inserted': result, 'note': '仅新增演示记录，无邮件或外部请求'}, ensure_ascii=False))
