import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update, delete
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import UserRole, require_roles
from app.domain.persistence import MaterialRecord
from app.domain.spares import SparePlanInput, SparePlanRecord
from app.services.spare_planning import analyze

router = APIRouter(prefix='/spare-plans', tags=['spare-plans'], dependencies=[Depends(require_roles(UserRole.ADMIN,UserRole.PROCUREMENT_MANAGER,UserRole.BUYER,UserRole.ANALYST))])
writer = require_roles(UserRole.ADMIN,UserRole.PROCUREMENT_MANAGER,UserRole.BUYER)

@router.get('/ranking')
def ranking(currency:str=Query('CNY',pattern='^[A-Z]{3}$'),days:int=Query(365,ge=30,le=1095),db:Session=Depends(get_db)):
    from app.services.spare_ranking import rank_spares
    return rank_spares(db,currency,days)


def checked(db, payload):
    if not db.scalar(select(MaterialRecord).where(MaterialRecord.code==payload.material_code,MaterialRecord.active.is_(True))):
        raise HTTPException(422,'请使用有效的现有物料编码')
    return analyze(payload)


def output(row):
    return {'id':row.id,**json.loads(row.payload),'version':row.version,'analysis':json.loads(row.result)}


@router.post('/analyze')
def preview(payload: SparePlanInput, db: Session=Depends(get_db)):
    return checked(db,payload)


@router.get('')
def listing(keyword: str='', page:int=Query(1,ge=1),page_size:int=Query(10,ge=1,le=100),db:Session=Depends(get_db)):
    clause=SparePlanRecord.material_code.contains(keyword,autoescape=True)
    return {'items':[output(r) for r in db.scalars(select(SparePlanRecord).where(clause).order_by(SparePlanRecord.id).offset((page-1)*page_size).limit(page_size))],'total':db.scalar(select(func.count()).select_from(SparePlanRecord).where(clause))}


@router.post('')
def create(payload:SparePlanInput,db:Session=Depends(get_db),user=Depends(writer)):
    result=checked(db,payload)
    row=SparePlanRecord(material_code=payload.material_code,payload=payload.model_dump_json(),result=json.dumps(result,ensure_ascii=False))
    db.add(row);db.commit();db.refresh(row)
    return output(row)


@router.put('/{plan_id}')
def edit(plan_id:str,payload:SparePlanInput,db:Session=Depends(get_db),user=Depends(writer)):
    result=checked(db,payload)
    changed=db.execute(update(SparePlanRecord).where(SparePlanRecord.id==plan_id,SparePlanRecord.version==payload.version).values(material_code=payload.material_code,payload=payload.model_dump_json(),result=json.dumps(result,ensure_ascii=False),version=payload.version+1))
    if changed.rowcount!=1:
        db.rollback();raise HTTPException(409,'记录已变化，请刷新后重试')
    db.commit()
    return output(db.get(SparePlanRecord,plan_id))


@router.delete('/{plan_id}',status_code=204)
def remove(plan_id:str,version:int,db:Session=Depends(get_db),user=Depends(writer)):
    changed=db.execute(delete(SparePlanRecord).where(SparePlanRecord.id==plan_id,SparePlanRecord.version==version))
    if changed.rowcount!=1:
        db.rollback();raise HTTPException(409,'记录已变化，请刷新后重试')
    db.commit()
