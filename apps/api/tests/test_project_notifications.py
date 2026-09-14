from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
H = {'X-User-Role': 'procurement_manager'}


def test_notification_lifecycle():
    staff = client.post('/api/v1/staff-users', headers=H, json={'user_code': uuid4().hex, 'name': '节点负责人'}).json()
    due = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    data = {'code': uuid4().hex, 'name': '通知测试项目', 'status': 'active', 'manager_id': staff['id'], 'tasks': [{'id': 't', 'name': '验收', 'owner_id': staff['id'], 'start': (due-timedelta(days=5)).isoformat(), 'finish': due.isoformat()}]}
    project = client.post('/api/v1/projects', headers=H, json=data).json()
    assert client.post('/api/v1/project-notifications/scan', headers=H).status_code == 200
    result = client.post('/api/v1/project-notifications/scan', headers=H).json()
    assert result['inserted'] == 0
    notifications = client.get('/api/v1/project-notifications', headers=H).json()['items']
    row = next(n for n in notifications if n['project_id'] == project['id'])
    url = '/api/v1/project-notifications/'+row['id']
    assert client.post(url+'/acknowledge', headers=H).status_code == 200
    assert client.post(url+'/acknowledge', headers=H).status_code == 409
    # No SMTP setup and no recipient email: must not attempt external delivery.
    assert client.post(url+'/send', headers=H).status_code == 409
    project['tasks'][0]['progress'] = 100
    assert client.put('/api/v1/projects/'+project['id'], headers=H, json=project).status_code == 200
    client.post('/api/v1/project-notifications/scan', headers=H)
    resolved = client.get('/api/v1/project-notifications?state=resolved', headers=H).json()['items']
    assert any(n['id'] == row['id'] for n in resolved)
    assert client.get('/api/v1/project-notifications', headers={'X-User-Role': 'buyer'}).status_code == 403


def test_mail_claim_prevents_duplicate(monkeypatch):
    from app.core.database import SessionLocal
    from app.domain.persistence import StaffUserRecord
    from app.domain.project_notifications import ProjectNotification
    from app.domain.supplier_portal import MailSettings
    from app.services import project_notifications as service

    sent = []
    class SMTP:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def starttls(self, **kwargs):
            pass
        def send_message(self, message):
            sent.append(message['To'])
    monkeypatch.setattr(service.smtplib, 'SMTP', SMTP)
    with SessionLocal() as db:
        settings = db.get(MailSettings, 1) or MailSettings(id=1)
        settings.host, settings.from_email, settings.username, settings.security = 'smtp.example.com', 'test@example.com', '', 'starttls'
        db.add(settings)
        staff = StaffUserRecord(user_code=uuid4().hex, name='邮件测试', email='owner@example.com', created_by='test')
        db.add(staff)
        db.flush()
        notice = ProjectNotification(event_key=uuid4().hex, project_id='test', task_id='t', owner_id=staff.id, subject='提醒', body='测试', kind='due_soon', created_at='2026-09-08')
        db.add(notice)
        db.commit()
        assert service.send(db, notice.id)['mail_status'] == 'sent'
        from fastapi import HTTPException
        try:
            service.send(db, notice.id)
            assert False, 'Duplicate send must be rejected'
        except HTTPException as exc:
            assert exc.status_code == 409
        assert sent == ['owner@example.com']
