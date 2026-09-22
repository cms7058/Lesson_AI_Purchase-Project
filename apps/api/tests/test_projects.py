from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.projects import ProjectInput
from app.main import app
from app.services.project_import import xml_preview

client = TestClient(app)
H = {'X-User-Role': 'procurement_manager'}


def test_project_crud_and_conflict():
    data = {'code': 'P-'+uuid4().hex[:8], 'name': '测试项目', 'tasks': [{'id': 't1', 'name': '设计'}]}
    r = client.post('/api/v1/projects', headers=H, json=data)
    assert r.status_code == 200, r.text
    row = r.json()
    assert client.get('/api/v1/projects', headers=H, params={'keyword': data['code']}).json()['total'] == 1
    row['name'] = '修改名称'
    updated = client.put('/api/v1/projects/'+row['id'], headers=H, json=row)
    assert updated.status_code == 200, updated.text
    assert updated.json()['version'] == 2
    assert client.put('/api/v1/projects/'+row['id'], headers=H, json=row).status_code == 409
    assert client.delete('/api/v1/projects/'+row['id']+'?version=2', headers=H).status_code == 204
    assert client.get('/api/v1/projects/'+row['id'], headers=H).status_code == 404


def test_graph_and_publishing():
    with pytest.raises(ValidationError):
        ProjectInput(code='A', name='A', tasks=[{'id': '1', 'name': 'a', 'predecessors': ['2']}, {'id': '2', 'name': 'b', 'predecessors': ['1']}])
    with pytest.raises(ValidationError):
        ProjectInput(code='A', name='A', status='active')
    assert client.get('/api/v1/projects', headers={'X-User-Role': 'buyer'}).json()['total'] == 0


def test_apqp_project_template_contains_quality_gates_and_ppap_tasks():
    response = client.get('/api/v1/projects/templates', headers=H)
    assert response.status_code == 200
    payload = response.json()
    assert payload['default_id'] == 'apqp-exhaust-weld-pipe-v1'
    template = payload['items'][0]
    assert template['project_type'] == 'apqp_exhaust_weld_pipe'
    assert template['gate_count'] == 6
    assert {item['code'] for item in template['quality_requirements']} >= {'APQP-1', 'APQP-3', 'PPAP'}
    assert any(item['apqp_stage'] == 'PPAP' for item in template['tasks'])


def test_create_apqp_project_automatically_applies_template():
    response = client.post('/api/v1/projects', headers=H, json={
        'code': 'APQP-AUTO-'+uuid4().hex[:8],
        'name': 'APQP自动载入验证',
        'template_id': 'apqp-exhaust-weld-pipe-v1',
        'project_type': 'apqp_exhaust_weld_pipe',
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload['tasks']) >= 20
    assert any(item['code'] == 'PPAP' for item in payload['quality_requirements'])


def test_xml_draft_no_persistence():
    raw = b'<Project><Name>Test</Name><Tasks><Task><UID>1</UID><Name>Design</Name><OutlineLevel>1</OutlineLevel><Start>2026-09-01T08:00:00</Start><Finish>2026-09-10T17:00:00</Finish></Task></Tasks></Project>'
    result = xml_preview(raw)
    assert result['draft']['status'] == 'draft'
    assert result['draft']['tasks'][0]['start'] == '2026-09-01'
    assert result['warnings']
    response = client.post('/api/v1/projects/import-xml', headers=H, files={'file': ('project.xml', raw)})
    assert response.status_code == 200
    assert response.json()['draft']['name'] == 'Test'
    assert client.post('/api/v1/projects/import-xml', headers=H, files={'file': ('bad.xml', b'<!DOCTYPE x><Project/>')}).status_code == 422


def test_dashboard_baseline_and_staff_reference():
    staff = client.post('/api/v1/staff-users', headers=H, json={'user_code': 'P-'+uuid4().hex[:8], 'name': '项目经理'}).json()
    payload = {'code': 'D-'+uuid4().hex[:8], 'name': '驾驶舱项目', 'manager_id': staff['id'], 'status': 'active', 'currency': 'USD', 'budget': 123,
               'tasks': [{'id': 'a', 'name': '交付', 'owner_id': staff['id'], 'start': '2026-09-01', 'finish': '2026-09-10'}]}
    response = client.post('/api/v1/projects', headers=H, json=payload)
    assert response.status_code == 200, response.text
    row = response.json()
    dashboard = client.get('/api/v1/projects/dashboard', headers=H, params={'currency': 'USD', 'manager_id': staff['id'], 'month': '2026-09'}).json()
    assert dashboard['project_count'] == 1 and dashboard['budget'] == 123 and dashboard['tasks'] == 1
    assert client.delete('/api/v1/staff-users/'+staff['id'], headers=H).status_code == 409
    url = '/api/v1/projects/'+row['id']
    assert client.post(url+'/baselines?version=1', headers=H).status_code == 200
    row['tasks'][0]['finish'] = '2026-09-15'
    assert client.put(url, headers=H, json=row).status_code == 200
    baseline = client.get(url+'/baselines', headers=H).json()['items'][0]
    assert baseline['changes'][0]['before'][1] == '2026-09-10'
    assert baseline['changes'][0]['after'][1] == '2026-09-15'
    assert client.post(url+'/baselines?version=1', headers=H).status_code == 409
