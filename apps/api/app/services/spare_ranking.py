import json
import math
from datetime import date, timedelta
from sqlalchemy import select
from app.domain.material_policy import MaterialPolicy
from app.domain.persistence import MaterialRecord, PurchaseOrderRecord, PurchaseOrderLineRecord
from app.domain.supply_feedback import SupplyFeedback


def rank_spares(db, currency='CNY', days=365, material_codes=None):
    end=date.today();start=end-timedelta(days=days)
    rows=[]
    materials={m.code:m for m in db.scalars(select(MaterialRecord).where(MaterialRecord.active.is_(True)))}
    for policy in db.scalars(select(MaterialPolicy)):
        c=json.loads(policy.payload);m=materials.get(policy.material_code)
        if not m or c['material_type']!='spare':continue
        demo=m.created_by=='spare-demo'
        history=list(db.execute(select(PurchaseOrderLineRecord,PurchaseOrderRecord).join(PurchaseOrderRecord,PurchaseOrderRecord.id==PurchaseOrderLineRecord.order_id).where(PurchaseOrderLineRecord.material_code==m.code,PurchaseOrderRecord.status!='cancelled',PurchaseOrderRecord.currency==currency,PurchaseOrderRecord.created_at>=start,PurchaseOrderRecord.created_at<end+timedelta(days=1))))
        quantity=sum(float(l.quantity) for l,o in history)
        amount=sum(float(l.quantity*l.unit_price) for l,o in history)
        cost=accepted=0;batch_ids=[]
        for f in db.scalars(select(SupplyFeedback).where(SupplyFeedback.material_code==m.code,SupplyFeedback.record_date>=start,SupplyFeedback.record_date<=end,SupplyFeedback.is_demo.is_(demo))):
            p=json.loads(f.payload_json)
            if not p.get('costs_confirmed') or p.get('currency')!=currency or p.get('unit')!=m.unit or not p.get('accepted_quantity'):continue
            cost+=p['received_quantity']*p['unit_price']*(1+p.get('tax_rate',0))+sum(p.get(k,0) for k in ('logistics_cost','rework_cost','delay_cost','other_cost'))-p.get('credit',0)
            accepted+=p['accepted_quantity'];batch_ids.append(f.id)
        unit_toc=cost/accepted if accepted else None
        reference_quantity=math.ceil(quantity/days*30) if quantity else 0
        # Explicit review policy, not fitted regression coefficients.
        factor={'A':3,'B':2,'C':1}[c['abc']]*{'V':3,'E':2,'D':1}[c['ved']]*{'F':3,'S':2,'N':1}[c['fsn']]
        score=reference_quantity*unit_toc*factor if unit_toc is not None and quantity else None
        rows.append({'material_code':m.code,'material_name':m.name,'specification':m.specification,'unit':m.unit,'classification':c,'history_quantity':quantity,'history_amount':round(amount,2),'order_count':len({o.id for l,o in history}),'reference_quantity':reference_quantity,'estimated_unit_price':round(amount/quantity,4) if quantity else 0,'unit_toc':round(unit_toc,4) if unit_toc is not None else None,'score':round(score,4) if score is not None else None,'batch_ids':batch_ids,'status':'可计算参考权重' if score is not None else '数据不足：需采购历史及同单位同币种确认成本批次'})
        rows[-1]['is_demo']=demo
        if demo:rows[-1]['status']='【演示】'+rows[-1]['status']
    selected=set(material_codes or [])
    for r in rows:
        pool=[x for x in rows if (not selected or x['material_code'] in selected)]
        total=sum(x['score'] or 0 for x in pool)
        r['weight']=round(r['score']/total*100,4) if r['score'] is not None and total and (not selected or r['material_code'] in selected) else None
        r['toc_weight_coefficient']=r['weight']
    rows.sort(key=lambda r:(r['weight'] is None,-(r['weight'] or 0),r['material_code']))
    return {'items':rows,'currency':currency,'start':start.isoformat(),'end':end.isoformat(),'policy':'review-v1','note':'TOC结果是采购优先权重系数，不是采购数量。权重得分基于历史需求强度、历史单位TOC及ABC/VED/FSN分类因子，并在本次候选备件范围内归一化；实际数量须结合需求、库存、在途和安全储备确认。'}
