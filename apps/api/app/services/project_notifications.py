import hashlib
import smtplib
import ssl
from datetime import datetime
from decimal import Decimal
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from sqlalchemy import select, update

from app.domain.persistence import PurchaseOrderLineRecord, PurchaseOrderRecord, StaffUserRecord
from app.domain.project_costs import ProjectAllocation
from app.domain.project_notifications import ProjectNotification
from app.domain.projects import ProjectRecord, project_data
from app.domain.supplier_portal import MailSettings
from app.services.rfq_mail import cipher


def scan(db):
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    active_keys = set()
    inserted = 0
    for project in db.scalars(select(ProjectRecord).where(ProjectRecord.status == 'active')):
        data = project_data(project)
        commitments = Decimal(0)
        allocations = db.execute(select(ProjectAllocation, PurchaseOrderLineRecord).join(PurchaseOrderLineRecord, ProjectAllocation.line_id == PurchaseOrderLineRecord.id).join(PurchaseOrderRecord, ProjectAllocation.order_id == PurchaseOrderRecord.id).where(ProjectAllocation.project_id == project.id, PurchaseOrderRecord.status.not_in(['draft', 'pending_approval', 'cancelled']))).all()
        for allocation, line in allocations:
            commitments += (allocation.quantity * line.unit_price * (1+line.tax_rate)).quantize(Decimal('.01'))
        if commitments > Decimal(str(data['budget'])) and data.get('manager_id'):
            key = hashlib.sha256(f"cost|{project.id}|{data['manager_id']}|{data['budget']}|{commitments}".encode()).hexdigest()
            active_keys.add(key)
            existing = db.scalar(select(ProjectNotification).where(ProjectNotification.event_key == key))
            if existing:
                if existing.state == 'resolved':
                    existing.state = 'open'
            else:
                db.add(ProjectNotification(event_key=key, project_id=project.id, task_id='', owner_id=data['manager_id'], subject=f'采购承诺超预算 · {project.code}'[:300],
                    body=f"项目：{project.name}\n项目总预算：{data['currency']} {data['budget']}\n含税采购承诺：{commitments}\n超预算：{commitments-Decimal(str(data['budget']))}\n仅比较有效订单分摊承诺，不代表实际已发生成本。请核查预算和采购分摊。", kind='cost_overrun', created_at=now.isoformat()))
                inserted += 1
        for task in data['tasks']:
            if task['kind'] == 'work_package' or task['progress'] == 100 or not task.get('finish') or not task.get('owner_id'):
                continue
            days = (datetime.fromisoformat(task['finish']).date()-now.date()).days
            if days > 3:
                continue
            kind = 'overdue' if days < 0 else 'due_soon'
            key = hashlib.sha256(f"{project.id}|{task['id']}|{task['finish']}|{task['owner_id']}|{kind}".encode()).hexdigest()
            active_keys.add(key)
            existing = db.scalar(select(ProjectNotification).where(ProjectNotification.event_key == key))
            if existing:
                if existing.state == 'resolved':
                    existing.state = 'open'
                continue
            title = f"{'里程碑' if task['kind']=='milestone' else '任务'}{'逾期' if days < 0 else '即将到期'}"
            db.add(ProjectNotification(event_key=key, project_id=project.id, task_id=task['id'], owner_id=task['owner_id'],
                subject=f'{title} · {project.code}'[:300], body=f"项目：{project.name}\n任务：{task['name']}\n计划完成：{task['finish']}\n请核实进度并在项目工作台更新。", kind=kind, created_at=now.isoformat()))
            inserted += 1
    for item in db.scalars(select(ProjectNotification).where(ProjectNotification.state.in_(['open', 'acknowledged']))):
        if item.event_key not in active_keys:
            item.state = 'resolved'
    db.flush()
    return inserted


def send(db, item_id):
    settings = db.get(MailSettings, 1)
    if not settings or not settings.host or not settings.from_email:
        raise HTTPException(409, '请先在邮件发送设置中配置SMTP')
    item = db.get(ProjectNotification, item_id)
    if not item or item.state == 'resolved':
        raise HTTPException(409, '提醒不存在或已解除')
    staff = db.get(StaffUserRecord, item.owner_id)
    if not staff or staff.status != 'active' or '@' not in staff.email or any(c in staff.email for c in '\r\n'):
        raise HTTPException(409, '负责人未配置有效邮箱或已停用')
    claimed = db.execute(update(ProjectNotification).where(ProjectNotification.id == item_id, ProjectNotification.mail_status == 'not_sent').values(mail_status='sending', recipient=staff.email))
    db.commit()
    if not claimed.rowcount:
        raise HTTPException(409, '该通知已发送或尝试过发送；请先核对发送结果，禁止重复发送')
    try:
        message = EmailMessage()
        message['From'], message['To'], message['Subject'] = settings.from_email, staff.email, item.subject
        message.set_content(item.body)
        factory = smtplib.SMTP_SSL if settings.security == 'ssl' else smtplib.SMTP
        options = {'context': ssl.create_default_context()} if settings.security == 'ssl' else {}
        with factory(settings.host, settings.port, timeout=15, **options) as server:
            if settings.security == 'starttls':
                server.starttls(context=ssl.create_default_context())
            if settings.username:
                password = cipher().decrypt(settings.password_encrypted.encode()).decode() if settings.password_encrypted else ''
                server.login(settings.username, password)
            server.send_message(message)
        item.mail_status = 'sent'
    except (OSError, smtplib.SMTPException, ValueError, InvalidToken):
        item.mail_status = 'uncertain'
        item.error = '发送未确认，请核查SMTP日志，勿直接重发以免重复通知'
    db.commit()
    return {'mail_status': item.mail_status, 'error': item.error}
