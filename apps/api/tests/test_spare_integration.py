import json
from datetime import date
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.domain.persistence import PurchaseOrderRecord, PurchaseOrderLineRecord
from app.domain.supply_feedback import SupplyFeedback

def test_classification_ranking_snapshot():
    h={'X-User-Role':'procurement_manager'}
    with TestClient(app) as c:
        code='SP-'+uuid4().hex
        classification={'material_type':'spare','abc':'A','ved':'V','fsn':'N','reason':'关键设备，年度消耗评审'}
        m=c.post('/api/v1/materials',headers=h,json={'code':code,'name':'轴承','spare_classification':classification}).json()
        assert m['spare_classification']==classification
        assert c.get('/api/v1/materials',params={'keyword':code},headers=h).json()['items'][0]['spare_classification']==classification
        with SessionLocal() as db:
            o=PurchaseOrderRecord(order_no=code,supplier_id='S',supplier_name='测试',factory_code='TEST',currency='CNY',status='completed',created_by='test')
            db.add(o);db.flush();db.add(PurchaseOrderLineRecord(order_id=o.id,material_code=code,material_name='轴承',quantity=120,unit='件',unit_price=10))
            db.add(SupplyFeedback(connector_id='test',external_id=code,supplier_code='S',material_code=code,record_date=date.today(),source_system='ERP',payload_json=json.dumps({'unit':'件','currency':'CNY','costs_confirmed':True,'received_quantity':120,'accepted_quantity':120,'unit_price':10,'tax_rate':0,'logistics_cost':120})))
            db.commit()
        ranking=c.get('/api/v1/spare-plans/ranking',headers=h).json()
        row=next(r for r in ranking['items'] if r['material_code']==code)
        assert row['unit_toc']==11 and row['weight']>0
        p={'title':'备件采购测试','factory_code':'TEST','spare_plan_codes':[code],'lines':[{'material_code':code,'material_name':'轴承','quantity':2}]}
        result=c.post('/api/v1/requisitions',headers=h,json=p)
        assert result.status_code==201,result.text
        saved=result.json();assert saved['spare_analysis_snapshot']['items'][0]['classification']==classification
        # A later classification update must not rewrite the saved analysis.
        c.put('/api/v1/materials/'+m['id'],headers=h,json={'spare_classification':{**classification,'ved':'E'}})
        rows=c.get('/api/v1/requisitions',headers=h).json()['items']
        assert next(r for r in rows if r['id']==saved['id'])['spare_analysis_snapshot']['items'][0]['classification']['ved']=='V'
        assert c.post('/api/v1/requisitions',headers=h,json={**p,'spare_plan_codes':['missing']}).status_code==422
