"""Add-only demo data. Stable IDs, one transaction, no mail or approval actions."""
import json
from datetime import datetime, timedelta
from uuid import uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo
from app.core.database import SessionLocal
from app.domain.persistence import MaterialRecord, SupplierRecord, FactoryRecord, MaterialCategoryRecord, MaterialCategoryAssignmentRecord, PurchaseOrderRecord, PurchaseOrderLineRecord
from app.domain.material_policy import MaterialPolicy
from app.domain.supply_feedback import SupplyFeedback, FeedbackRow

def uid(s):return str(uuid5(NAMESPACE_URL,'pebs-spare-demo-v1:'+s))

def seed(db):
    counts={};now=datetime.now(ZoneInfo('Asia/Shanghai'))
    def put(model,key,**values):
        row=db.get(model,uid(key))
        if row:return row
        row=model(id=uid(key),**values);db.add(row);db.flush();counts[model.__tablename__]=counts.get(model.__tablename__,0)+1
        return row
    supplier=put(SupplierRecord,'supplier',code='DEMO-SP-S01',name='【演示】备件配套供应商',status='qualified',created_by='spare-demo')
    factory=put(FactoryRecord,'factory',code='DEMO-SP-F01',name='【演示】设备维修工厂',created_by='spare-demo')
    parent=None
    for level,name in enumerate(['【演示】备品备件','【演示】设备配套','【演示】通用备件'],1):
        parent=put(MaterialCategoryRecord,'category'+str(level),code='DSP'+('-01'*(level-1)),name=name,level=level,parent_id=parent.id if parent else None,path_name=' / '.join(['演示备件']*level),created_by='spare-demo')
    specs=[('伺服驱动器','A','V','S',5800,8),('精密主轴轴承','A','V','F',2400,30),('液压泵总成','A','E','S',3800,12),('气动电磁阀','B','E','F',350,80),('变频器风扇','B','D','S',180,40),('密封圈套件','C','V','F',28,200),('过滤器滤芯','C','E','F',45,150),('停产设备联轴器','B','D','N',760,3),('事故备用控制板','A','V','N',9000,0)]
    for i,(name,abc,ved,fsn,price,qty) in enumerate(specs,1):
        code=f'DEMO-SP-{i:03}'
        # A pre-existing material means the entire scenario is left untouched.
        if db.get(MaterialRecord,uid(code)):continue
        m=put(MaterialRecord,code,code=code,name='【演示】'+name,specification='模拟规格，仅演示',unit='件',standard_price=price,lead_time_days=7+i*3,created_by='spare-demo')
        db.add(MaterialPolicy(material_code=code,payload=json.dumps({'material_type':'spare','abc':abc,'ved':ved,'fsn':fsn,'reason':'【演示】模拟年度价值、设备关键性和消耗流动性评审；不代表实际设备数据'},ensure_ascii=False)))
        put(MaterialCategoryAssignmentRecord,code+'cat',material_id=m.id,category_id=parent.id)
        if not qty:continue
        for j in range(3):
            day=now-timedelta(days=25+j*55+i)
            order=put(PurchaseOrderRecord,code+'po'+str(j),order_no=f'DEMO-SP-PO-{i:02}-{j+1}',supplier_id=supplier.code,supplier_name=supplier.name,factory_code=factory.code,currency='CNY',status='completed',created_by='spare-demo',created_at=day)
            db.add(PurchaseOrderLineRecord(order_id=order.id,material_code=code,material_name=m.name,quantity=qty,unit='件',unit_price=price,delivery_date=day.date()))
            payload=FeedbackRow(external_id=code+'batch'+str(j),supplier_code=supplier.code,material_code=code,record_date=day.date(),received_quantity=qty,inspected_quantity=qty,accepted_quantity=max(1,qty-j),on_time_quantity=max(0,qty-j-1),rework_quantity=j,unit_price=price,logistics_cost=qty*3,rework_cost=j*40,delay_cost=j*120,response_hours=4+j*3,costs_confirmed=True)
            put(SupplyFeedback,code+'feedback'+str(j),connector_id='spare-demo',external_id=payload.external_id,supplier_code=supplier.code,material_code=code,record_date=day.date(),source_system='DEMO',is_demo=True,payload_json=payload.model_dump_json())
    db.commit();return counts

if __name__=='__main__':
    from app.main import app  # register/create development schema
    with SessionLocal() as db:print(json.dumps(seed(db),ensure_ascii=False))
