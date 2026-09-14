from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app

H={'X-User-Role':'procurement_manager'}


def test_spare_plan_constraints_crud_and_stale_write():
    with TestClient(app) as c:
        code='SP-'+uuid4().hex
        assert c.post('/api/v1/materials',headers=H,json={'code':code,'name':'备件测试'}).status_code==201
        scenario={'name':'低价迟到','quantity':5,'unit_price':10,'arrival':'2027-02-03','risk_percent':10,'evidence':'人工评估场景'}
        p={'material_code':code,'abc':'A','ved':'V','fsn':'N','classification_reason':'设备停机影响大','as_of':'2027-01-01','required_date':'2027-02-01','horizon_end':'2027-03-01','demand':5,'budget':10000,'data_source':'测试快照','risk_limit_v':1,'risk_limit_e':5,'risk_limit_d':15,'scenarios':[scenario,{**scenario,'name':'保障方案','unit_price':20,'arrival':'2027-01-20','risk_percent':0.5}]}
        r=c.post('/api/v1/spare-plans',headers=H,json=p)
        assert r.status_code==200,r.text
        row=r.json();assert row['analysis']['recommended']=='保障方案'
        assert len(row['analysis']['scenarios'][0]['reasons'])==2
        url='/api/v1/spare-plans/'+row['id']
        assert c.put(url,headers=H,json={**p,'budget':1}).json()['analysis']['recommended'] is None
        assert c.put(url,headers=H,json=p).status_code==409
        assert c.get('/api/v1/spare-plans',headers=H,params={'keyword':code}).json()['total']==1
        assert c.post('/api/v1/spare-plans',headers={'X-User-Role':'analyst'},json=p).status_code==403
        assert c.post('/api/v1/spare-plans/analyze',headers=H,json={**p,'risk_limit_v':99}).status_code==422
        assert c.post('/api/v1/spare-plans/analyze',headers=H,json={**p,'material_code':'missing'}).status_code==422
        assert c.delete(url,headers=H,params={'version':1}).status_code==409
        assert c.delete(url,headers=H,params={'version':2}).status_code==204
