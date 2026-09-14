from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
H = {'X-User-Role': 'procurement_manager'}


def test_schedule_and_permissions():
    code = uuid4().hex
    staff = client.post('/api/v1/staff-users', headers=H, json={'user_code': code, 'name': '计划员'}).json()
    project = client.post('/api/v1/projects', headers=H, json={'code': code, 'name': '拖动测试', 'tasks': [
        {'id': 'a', 'name': '设计', 'start': '2026-09-01', 'finish': '2026-09-03'},
        {'id': 'b', 'name': '采购', 'start': '2026-09-05', 'finish': '2026-09-07', 'predecessors': ['a']},
        {'id': 'c', 'name': '独立任务', 'start': '2026-09-01', 'finish': '2026-09-02'}]}).json()
    result = client.post('/api/v1/projects/schedule-preview', headers=H, json={'project': project, 'task_id': 'a', 'days': 2}).json()
    assert result['tasks'][0]['start'] == '2026-09-03'
    assert result['tasks'][1]['start'] == '2026-09-07'
    assert result['tasks'][2]['start'] == '2026-09-01'
    assert client.post('/api/v1/projects/schedule-preview', headers=H, json={'project': project, 'task_id': 'b', 'days': -3}).status_code == 409
    user = {'X-User-Role': 'buyer', 'X-User-Id': code}
    url = '/api/v1/projects/'+project['id']
    assert client.get(url, headers=user).status_code == 403
    grant = {'project_id': project['id'], 'staff_id': staff['id'], 'role': 'viewer', 'valid_from': '2026-01-01', 'valid_to': '2099-01-01'}
    response = client.post('/api/v1/project-grants', headers=H, json=grant)
    assert response.status_code == 200, response.text
    gid = response.json()['id']
    assert client.get(url, headers=user).status_code == 200
    assert client.put(url, headers=user, json=project).status_code == 403
    grant['role'] = 'planner'
    assert client.put('/api/v1/project-grants/'+gid, headers=H, json=grant).status_code == 200
    project['tasks'] = result['tasks']
    assert client.put(url, headers=user, json=project).status_code == 200
    project['budget'] = 999
    assert client.put(url, headers=user, json=project).status_code == 403
    assert client.delete('/api/v1/project-grants/'+gid, headers=H).status_code == 204
    assert client.get(url, headers=user).status_code == 403
