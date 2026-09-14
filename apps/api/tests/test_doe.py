import itertools
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_doe_count_persistence_diagnostics():
    with TestClient(app) as c:
        h={'X-User-Role':'procurement_manager'};code='DOE-'+uuid4().hex
        c.post('/api/v1/materials',headers=h,json={'code':code,'name':'DOE测试'})
        p={'material_code':code,'factors':[{'name':'A','low':0,'high':10},{'name':'B','low':20,'high':30}]}
        assert c.post('/api/v1/toc-doe',headers=h,json={**p,'runs':5}).status_code==422
        r=c.post('/api/v1/toc-doe',headers=h,json=p);assert r.status_code==200,r.text
        s=r.json();assert s['runs']==6 and s['diagnostics']['status']=='待执行/待补齐'
        responses=[100+5*r['coded'][0]+2*r['coded'][1]+i*.1 for i,r in enumerate(s['design'])]
        r=c.put('/api/v1/toc-doe/'+s['id'],headers=h,json={'values':responses,'evidence':'模拟响应测试','version':1,'simulated':True})
        assert r.status_code==200,r.text
        d=r.json()['diagnostics'];assert d['rank']==3 and len(d['qq'])==6 and d['lack_of_fit']['pure_error_df']==1
        assert '模拟' in d['status']
        assert c.get('/api/v1/toc-doe',headers=h,params={'material_code':code}).json()['items'][0]['version']==2

        screening={**p,'factors':[{'name':f'因素{i}','low':0,'high':1} for i in range(6)],'runs':30,'design_kind':'screening'}
        r=c.post('/api/v1/toc-doe',headers=h,json=screening);assert r.status_code==200,r.text
        assert r.json()['runs']==30
        assert '筛选设计' in r.json()['method']
        study=r.json()
        responses=[100+sum((j+1)*v*3 for j,v in enumerate(row['coded']))+((row['run']%3)-1)*.01 for row in study['design']]
        verified=c.put('/api/v1/toc-doe/'+study['id'],headers=h,json={'values':responses,'evidence':'DOE-TEST-001 实际试验记录','version':1,'simulated':False})
        assert verified.status_code==200,verified.text
        diagnostics=verified.json()['diagnostics']
        assert diagnostics['passed'] and diagnostics['cross_validation']['folds']==5
        assert len(diagnostics['factor_validation'])==6
        assert all(item['eligible'] for item in diagnostics['factor_validation'])

        spare={**p,'model_fingerprint':'spare-classification-doe-v2','factors':[{'name':name,'low':1,'high':3} for name in ('ABC','VED','FSN')],'runs':30,'design_kind':'three_level'}
        r=c.post('/api/v1/toc-doe',headers=h,json=spare);assert r.status_code==200,r.text
        assert r.json()['recommended_minimum']==30
        assert len(r.json()['design'])==30
        assert {tuple(x['levels']) for x in r.json()['design']}==set(itertools.product((1,2,3),repeat=3))
        filtered=c.get('/api/v1/toc-doe',headers=h,params={'material_code':code,'model_fingerprint':'spare-classification-doe-v2'}).json()['items']
        assert len(filtered)==1 and filtered[0]['design_kind']=='three_level'
        # Category filters must not confuse a free-text reason with a type.
        assert c.get('/api/v1/materials',headers=h,params={'keyword':code,'material_type':'production'}).json()['total']==1
        assert c.get('/api/v1/materials',headers=h,params={'keyword':code,'material_type':'spare'}).json()['total']==0
