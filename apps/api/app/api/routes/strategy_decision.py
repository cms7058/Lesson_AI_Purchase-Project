import json
from datetime import date, timedelta, datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, Text, DateTime, func, select
from sqlalchemy.orm import Mapped, mapped_column, Session
from app.core.database import Base, get_db
from app.core.security import CurrentUser, get_current_user, require_roles, UserRole
from app.domain.persistence import MaterialRecord
from app.domain.material_policy import MaterialPolicy
from app.domain.spare_operations import SpareStockRecord
from app.services.strategy_decision import DecisionInput, analyze

class DecisionSnapshot(Base):
    __tablename__='spare_strategy_decisions'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    material_code: Mapped[str]=mapped_column(String(64),index=True)
    payload: Mapped[str]=mapped_column(Text)
    result: Mapped[str]=mapped_column(Text)
    actor: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime,server_default=func.now())

router=APIRouter(prefix='/strategy-decisions',tags=['strategy-decisions'],dependencies=[Depends(require_roles(UserRole.ADMIN,UserRole.PROCUREMENT_MANAGER,UserRole.BUYER,UserRole.ANALYST))])

def material(db,code):
    m=db.scalar(select(MaterialRecord).where(MaterialRecord.code==code,MaterialRecord.active.is_(True)))
    policy=db.get(MaterialPolicy,code)
    if not m or not policy or json.loads(policy.payload).get('material_type')!='spare':
        raise HTTPException(422,'请选择有效备件物料')
    return m

@router.get('/{code}/context')
def context(code:str,db:Session=Depends(get_db)):
    m=material(db,code)
    stocks=list(db.scalars(select(SpareStockRecord).where(SpareStockRecord.material_code==code)))
    return {'material_code':code,'name':m.name,'classification':json.loads(db.get(MaterialPolicy,code).payload),'inventory':sum(float(s.quantity) for s in stocks if s.condition=='good' and s.lifecycle_status=='in_stock'),'stock_rows':len(stocks),'note':'仅提供良好在库数量参考，请扣除预留及不可调拨部分后确认；跨仓合计不代表可即时使用。'}

@router.post('/{code}/preview')
def preview(code:str,p:DecisionInput,db:Session=Depends(get_db)):
    material(db,code);return analyze(p)

@router.post('/{code}',status_code=201)
def save(code:str,p:DecisionInput,db:Session=Depends(get_db),u:CurrentUser=Depends(require_roles(UserRole.ADMIN,UserRole.PROCUREMENT_MANAGER,UserRole.BUYER))):
    material(db,code);result=analyze(p)
    row=DecisionSnapshot(material_code=code,payload=p.model_dump_json(),result=json.dumps(result,ensure_ascii=False,default=str),actor=u.user_id)
    db.add(row);db.commit();db.refresh(row)
    return {'id':row.id,'created_at':row.created_at,'result':result}

@router.get('/{code}/history')
def history(code:str,page:int=Query(1,ge=1),page_size:int=Query(10,ge=1,le=50),db:Session=Depends(get_db)):
    material(db,code)
    q=select(DecisionSnapshot).where(DecisionSnapshot.material_code==code)
    rows=db.scalars(q.order_by(DecisionSnapshot.created_at.desc(),DecisionSnapshot.id.desc()).offset((page-1)*page_size).limit(page_size))
    return {'items':[{'id':r.id,'created_at':r.created_at,'actor':r.actor,'input':json.loads(r.payload),'result':json.loads(r.result)} for r in rows],'total':db.scalar(select(func.count()).select_from(DecisionSnapshot).where(DecisionSnapshot.material_code==code))}

@router.get('/{code}/example')
def example(code:str,db:Session=Depends(get_db)):
    material(db,code)
    return {'quantity':10,'required_date':str(date.today()+timedelta(days=7)),'budget':1500,'baseline_price':100,'premium_limit':20,'risk_limit':10,'downtime_per_day':500,'annual_issues':1,'critical':True,'reserve':2,'available':2,'inventory_confirmed':True,'owner':'演示采购经理','evidence':'【模拟】需求及库存仅演示，CNY同口径费用；不代表真实采购依据','simulated':True,'candidates':[{'name':name,'source':source,'supply_mode':mode,'unit_price':price,'fees':50,'holding_cost':20,'validation_cost':validation,'arrival':str(date.today()+timedelta(days=days)),'validated':valid,'reliability':reliability,'evidence':'【模拟】报价、交期与履约数据'} for name,source,mode,price,days,valid,reliability,validation in [('原厂常规','oem','standard',100,12,True,98,0),('原厂加急','oem','framework',115,5,True,98,0),('国产待验证','domestic','standard',70,4,False,92,100),('寄售保障','alternative','consignment',90,3,True,96,0)]]}
