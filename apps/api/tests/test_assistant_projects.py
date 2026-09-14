from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
H = {'X-User-Role': 'procurement_manager'}


def test_project_conversation_scope_and_followup():
    code = 'AI-' + uuid4().hex
    project = client.post('/api/v1/projects', headers=H, json={'code':code,'name':code,'tasks':[{'id':'a','name':'测试逾期任务','start':'2020-01-01','finish':'2020-01-02'}]}).json()
    def ask(message, headers=H, **kwargs):
        response = client.post('/api/v1/assistant/chat', headers=headers, json={'message':message,**kwargs})
        assert response.status_code == 200
        return response.json()
    assert ask('查询项目 '+code)['result']['total'] == 1
    assert ask('其中逾期任务', history=[{'role':'user','content':'查询项目 '+code}])['result']['rows'][0]['name'] == '测试逾期任务'
    assert ask('查询项目 '+code, {'X-User-Role':'buyer','X-User-Id':uuid4().hex})['result']['total'] == 0
    assert ask('查询项目 MISSING-123')['result']['total'] == 0
    assert ask('查询订单', history=[{'role':'user','content':'查询项目'}])['result']['resource'] != 'projects'
    assert client.get('/api/v1/projects/'+project['id'],headers=H).json()['tasks'][0]['start'] == '2020-01-01'
