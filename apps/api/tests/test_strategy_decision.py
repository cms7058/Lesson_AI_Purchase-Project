from fastapi.testclient import TestClient
from uuid import uuid4
from app.main import app
from app.services.strategy_decision import DecisionInput, analyze

def test_missing_data_never_produces_recommendation():
    result=analyze(DecisionInput())
    assert result['missing'] and result['recommendation'] is None
    assert result['net_quantity'] is None

def test_decision_constraints_snapshots_and_recalculation():
    h={'X-User-Role':'procurement_manager'}
    with TestClient(app) as c:
        code='SD-'+uuid4().hex[:10]
        assert c.post('/api/v1/materials',headers=h,json={'code':code,'name':'策略分析备件','spare_classification':{'material_type':'spare','abc':'A','ved':'V','fsn':'N','reason':'测试评审'}}).status_code==201
        p=c.get(f'/api/v1/strategy-decisions/{code}/example',headers=h).json()
        result=c.post(f'/api/v1/strategy-decisions/{code}/preview',headers=h,json=p).json()
        assert result['recommendation']=='原厂加急'
        assert result['candidates'][1]['cost']==1220
        assert {'交期冲突','技术约束','供货协议待核验','长尾与保障'} <= {x['type'] for x in result['conflicts']}
        saved=c.post(f'/api/v1/strategy-decisions/{code}',headers=h,json=p)
        assert saved.status_code==201
        p['budget']=100
        blocked=c.post(f'/api/v1/strategy-decisions/{code}/preview',headers=h,json=p).json()
        assert blocked['recommendation'] is None
        history=c.get(f'/api/v1/strategy-decisions/{code}/history',headers=h).json()
        assert history['items'][0]['result']['recommendation']=='原厂加急'
        assert history['items'][0]['input']['simulated'] is True
        p['budget']=1500
        p['candidates'][3]['agreement_reviewed']=True
        reviewed=c.post(f'/api/v1/strategy-decisions/{code}/preview',headers=h,json=p).json()
        assert reviewed['recommendation']=='寄售保障'
        assert not any(x['type']=='供货协议待核验' for x in reviewed['conflicts'])
        p['available']=12
        covered=c.post(f'/api/v1/strategy-decisions/{code}/preview',headers=h,json=p).json()
        assert covered['recommendation'] is None and covered['net_quantity']==0
        p['candidates'][0]['unit_price']=-1
        assert c.post(f'/api/v1/strategy-decisions/{code}/preview',headers=h,json=p).status_code==422
        assert c.post(f'/api/v1/strategy-decisions/{code}',headers={'X-User-Role':'analyst'},json={}).status_code==403
