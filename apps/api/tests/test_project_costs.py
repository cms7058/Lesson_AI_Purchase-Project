from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
H = {'X-User-Role': 'procurement_manager'}


def test_cost_allocation_and_warning():
    tag = uuid4().hex
    staff = client.post('/api/v1/staff-users', headers=H, json={'user_code': tag, 'name': '成本经理'}).json()
    project = client.post('/api/v1/projects', headers=H, json={'code': tag, 'name': '成本测试', 'budget': 100, 'status': 'active', 'manager_id': staff['id'], 'tasks': [{'id': 't', 'name': '采购', 'owner_id': staff['id'], 'start': '2026-01-01', 'finish': '2026-01-02'}]}).json()
    order = client.post('/api/v1/orders', headers=H, json={'supplier_id': 'test', 'supplier_name': '测试', 'factory_code': 'F', 'lines': [{'material_code': tag, 'material_name': '物料', 'quantity': 10, 'unit': '件', 'unit_price': 100, 'tax_rate': .13}]}).json()
    line = client.get('/api/v1/project-costs/lines', headers=H, params={'keyword': order['order_no']}).json()['items'][0]
    url = '/api/v1/project-costs/'+project['id']
    response = client.post(url, headers=H, json={'line_id': line['id'], 'task_id': 't', 'quantity': 2})
    assert response.status_code == 200, response.text
    allocation = response.json()['id']
    assert client.get(url, headers=H).json()['draft'] == 226
    assert client.post(url, headers=H, json={'line_id': line['id'], 'quantity': 9}).status_code == 409
    assert client.patch('/api/v1/orders/'+order['id'], headers=H, json={'lines': order['lines']}).status_code == 409
    assert client.delete('/api/v1/orders/'+order['id'], headers=H).status_code == 409
    assert client.patch('/api/v1/orders/'+order['id'], headers=H, json={'status': 'approved'}).status_code == 200
    costs = client.get(url, headers=H).json()
    assert costs['committed'] == 226 and costs['over_budget']
    client.post('/api/v1/project-notifications/scan', headers=H)
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.domain.project_notifications import ProjectNotification
    with SessionLocal() as db:
        notices = list(db.scalars(select(ProjectNotification).where(ProjectNotification.project_id == project['id'], ProjectNotification.kind == 'cost_overrun')))
        assert len(notices) == 1 and notices[0].state == 'open'
    assert client.patch('/api/v1/orders/'+order['id'], headers=H, json={'status': 'cancelled'}).status_code == 200
    assert client.get(url, headers=H).json()['committed'] == 0
    client.post('/api/v1/project-notifications/scan', headers=H)
    with SessionLocal() as db:
        assert db.scalar(select(ProjectNotification).where(ProjectNotification.project_id == project['id'], ProjectNotification.kind == 'cost_overrun')).state == 'resolved'
    assert client.delete(url+'/'+allocation, headers=H).status_code == 204
