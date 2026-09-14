"""Seed clearly simulated three-factor spare classification DOE records; never overwrite."""
import itertools
import json
import random
from uuid import uuid5,NAMESPACE_URL
from sqlalchemy import select
from app.api.routes.doe import DoeRecord, diagnostics
from app.core.database import SessionLocal
from app.domain.persistence import MaterialRecord

def seed(db):
    count=0
    for i,m in enumerate(db.scalars(select(MaterialRecord).where(MaterialRecord.created_by=='spare-demo').order_by(MaterialRecord.code))):
        key=str(uuid5(NAMESPACE_URL,'pebs-spare-doe-demo-v2:'+m.code))
        if db.get(DoeRecord,key):continue
        factors=[{'name':'ABC价值等级（C=1/B=2/A=3）','low':1,'high':3},{'name':'VED关键性等级（D=1/E=2/V=3）','low':1,'high':3},{'name':'FSN流动性等级（N=1/S=2/F=3）','low':1,'high':3}]
        points=list(itertools.product([-1,0,1],repeat=3))+[(0,0,0)]*3
        random.Random(620+i).shuffle(points)
        design=[{'run':j+1,'coded':list(point),'levels':[value+2 for value in point]} for j,point in enumerate(points)]
        values=[round(10+15*(point[0]+2)+12*(point[1]+2)+8*(point[2]+2)+2*point[0]*point[1]+(((j*5+i)%7)-3)*.25,4) for j,point in enumerate(points)]
        study={'material_code':m.code,'model_fingerprint':'spare-classification-doe-v2','design_kind':'three_level','factors':factors,'recommended_minimum':30,'runs':30,'seed':620+i,'design':design,'values':values,'simulated':True,'evidence':'【演示】ABC/VED/FSN三水平分类组合的模拟响应，未执行真实业务试验。','version':1,'method':'【演示】三水平全因子＋3次中心重复；分类主效应诊断','note':'27种ABC/VED/FSN组合加3次中心重复，仅用于演示采购优先权重响应分析，不代表真实DOE验证通过，也不输出采购数量。'}
        diagnostics(study)
        db.add(DoeRecord(id=key,material_code=m.code,payload=json.dumps(study,ensure_ascii=False)));count+=1
    db.commit();return {'created_studies':count,'simulated_runs':count*30}

if __name__=='__main__':
    from app.main import app
    with SessionLocal() as db:print(seed(db))
