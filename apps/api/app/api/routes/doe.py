"""Full factorial main-effect designs; diagnostics never imply causal validation."""
import itertools
import json
import random
from typing import Literal
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from scipy import stats
from sqlalchemy import String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base, get_db
from app.core.security import UserRole, require_roles


class DoeRecord(Base):
    __tablename__='toc_doe_studies'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    material_code:Mapped[str]=mapped_column(String(64),index=True)
    payload:Mapped[str]=mapped_column(Text)

class Factor(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    low:float=Field(ge=-1e12,le=1e12,allow_inf_nan=False)
    high:float=Field(ge=-1e12,le=1e12,allow_inf_nan=False)
    @model_validator(mode='after')
    def bounds(self):
        if self.low>=self.high:raise ValueError('高水平必须大于低水平')
        return self

class Design(BaseModel):
    material_code:str=Field(min_length=1,max_length=64)
    model_fingerprint:str=Field(default='unfitted',max_length=200)
    factors:list[Factor]=Field(min_length=1,max_length=6)
    runs:int|None=Field(default=None,ge=4,le=128)
    seed:int=Field(default=42,ge=0,le=2147483647)
    design_kind:Literal['full_factorial','screening','three_level']='full_factorial'
    @model_validator(mode='after')
    def names(self):
        if len({x.name for x in self.factors})!=len(self.factors):raise ValueError('因素名称不能重复')
        return self

class Observations(BaseModel):
    values:list[float|None]=Field(min_length=1,max_length=128)
    evidence:str=Field(min_length=1,max_length=4000)
    version:int=Field(ge=1)
    simulated:bool=True

router=APIRouter(prefix='/toc-doe',tags=['toc-doe'],dependencies=[Depends(require_roles(UserRole.ADMIN,UserRole.PROCUREMENT_MANAGER,UserRole.BUYER,UserRole.ANALYST))])

def diagnostics(study):
    values=study['values'];completed=sum(v is not None for v in values)
    if completed<len(values):return {'status':'待执行/待补齐','completed':completed}
    x=np.array([[1,*r['coded']] for r in study['design']],float);y=np.array(values,float)
    b=np.linalg.lstsq(x,y,rcond=None)[0];pred=x@b;res=y-pred
    rank=int(np.linalg.matrix_rank(x));residual_df=len(values)-x.shape[1]
    mse=float(res@res/residual_df) if residual_df>0 else None
    covariance=np.linalg.pinv(x.T@x)
    standard_errors=np.sqrt(np.diag(covariance)*mse) if mse is not None else np.full(x.shape[1],np.nan)
    t_values=np.divide(b,standard_errors,out=np.zeros_like(b),where=standard_errors>1e-12)
    p_values=(2*stats.t.sf(abs(t_values),residual_df)).tolist() if residual_df>0 else [None]*len(b)
    fold_count=min(5,max(2,len(values)//6));folds=np.arange(len(values))%fold_count
    cv_pred=np.full(len(values),np.nan);fold_coefficients=[]
    for fold in range(fold_count):
        train=folds!=fold;test=~train
        if train.sum()<x.shape[1] or np.linalg.matrix_rank(x[train])<x.shape[1]:continue
        fold_b=np.linalg.lstsq(x[train],y[train],rcond=None)[0]
        cv_pred[test]=x[test]@fold_b;fold_coefficients.append(fold_b)
    cv_complete=bool(np.isfinite(cv_pred).all())
    cv_error=y-cv_pred if cv_complete else np.array([])
    cv_total=float(np.sum((y-y.mean())**2))
    cv={
        'folds':fold_count,
        'predicted':cv_pred.tolist() if cv_complete else [],
        'mae':float(np.mean(abs(cv_error))) if cv_complete else None,
        'rmse':float(np.sqrt(np.mean(cv_error**2))) if cv_complete else None,
        'r_squared':1-float(cv_error@cv_error)/cv_total if cv_complete and cv_total>1e-12 else None,
    }
    fold_array=np.array(fold_coefficients) if fold_coefficients else np.empty((0,x.shape[1]))
    factor_validation=[]
    for index,factor in enumerate(study['factors'],1):
        fold_values=fold_array[:,index] if len(fold_array) else np.array([])
        sign_consistency=float(max(np.mean(fold_values>=0),np.mean(fold_values<=0))) if len(fold_values) else 0
        coefficient_cv=float(np.std(fold_values)/max(abs(np.mean(fold_values)),1e-12)) if len(fold_values) else None
        reasons=[]
        if p_values[index] is None or p_values[index]>.05:reasons.append('主效应p值>0.05')
        if sign_consistency<.8:reasons.append('交叉验证系数方向不稳定')
        if coefficient_cv is None or coefficient_cv>.5:reasons.append('交叉验证系数波动>50%')
        if cv['r_squared'] is None or cv['r_squared']<=0:reasons.append('交叉验证R²≤0')
        factor_validation.append({'name':factor['name'],'coefficient':float(b[index]),'p_value':p_values[index],'sign_consistency':sign_consistency,'coefficient_cv':coefficient_cv,'eligible':not reasons and not study['simulated'],'diagnostic_passed':not reasons,'reasons':reasons or (['模拟试验不能作为正式定价系数'] if study['simulated'] else [])})
    groups={}
    for r,value in zip(study['design'],values):groups.setdefault(tuple(r['coded']),[]).append(value)
    pure=sum(sum((np.array(v)-np.mean(v))**2) for v in groups.values());df_pure=len(values)-len(groups)
    df_lof=len(groups)-x.shape[1];lof=max(0,float(res@res)-pure)
    f=(lof/df_lof)/(pure/df_pure) if pure>0 and df_lof>0 and df_pure>0 else None
    theoretical,ordered=stats.probplot(res,fit=False)
    formal=not study['simulated'] and bool(study.get('evidence','').strip()) and rank==x.shape[1] and all(item['eligible'] for item in factor_validation)
    return {'status':'正式DOE交叉验证通过' if formal else ('模拟诊断（禁止用于定价）' if study['simulated'] else 'DOE交叉验证未通过'),'passed':formal,'completed':completed,'coefficients':b.tolist(),'standard_errors':standard_errors.tolist(),'p_values':p_values,'predicted':pred.tolist(),'residuals':res.tolist(),'rmse':float(np.sqrt(np.mean(res**2))),'rank':rank,'residual_df':residual_df,'qq':list(map(list,zip(theoretical.tolist(),ordered.tolist()))),'cross_validation':cv,'factor_validation':factor_validation,'lack_of_fit':{'pure_error':float(pure),'pure_error_df':df_pure,'lack_of_fit_df':df_lof,'f':f,'p':float(stats.f.sf(f,df_lof,df_pure)) if f is not None else None,'note':'纯误差为零或自由度不足时不计算F检验；不显著不证明模型正确。'}}

@router.post('')
def create(p:Design,db:Session=Depends(get_db)):
    from app.domain.persistence import MaterialRecord
    if not db.scalar(select(MaterialRecord).where(MaterialRecord.code==p.material_code)):
        raise HTTPException(422,'物料不存在')
    corners=list(itertools.product([-1,1],repeat=len(p.factors)))
    minimum=3**len(p.factors)+3 if p.design_kind=='three_level' else (max(12,len(p.factors)*2+2) if p.design_kind=='screening' else len(corners)+2)
    n=p.runs or minimum
    if n<minimum:raise HTTPException(422,f'本设计至少{minimum}次；请增加试验次数或减少因素')
    rng=random.Random(p.seed)
    if p.design_kind=='three_level':
        points=list(itertools.product([-1,0,1],repeat=len(p.factors)))+[tuple([0]*len(p.factors))]*(n-3**len(p.factors))
    elif p.design_kind=='screening':
        candidates=corners[:];rng.shuffle(candidates)
        points=candidates[:n-2]+[tuple([0]*len(p.factors))]*2
        while len(points)<n:points.append(rng.choice(corners))
    else:points=corners+[tuple([0]*len(p.factors))]*(n-len(corners))
    rng.shuffle(points)
    design=[{'run':i+1,'coded':list(row),'levels':[f.low+(v+1)/2*(f.high-f.low) for f,v in zip(p.factors,row)]} for i,row in enumerate(points)]
    method='三水平全因子＋中心点重复；分类主效应模型' if p.design_kind=='three_level' else ('两水平筛选设计＋中心点；一阶主效应模型' if p.design_kind=='screening' else '两水平全因子＋中心点重复；一阶主效应模型')
    study={**p.model_dump(),'recommended_minimum':minimum,'runs':n,'design':design,'values':[None]*n,'simulated':True,'evidence':'','version':1,'method':method,'note':'须先确认各指标水平代表可执行的采购或供应方案，并完成安全及业务评审。建议次数未基于实际效应大小、噪声与功效计算；不保证验证充分。新拟合DOE模型的诊断不等于原TOC模型的独立预测验证。'}
    row=DoeRecord(material_code=p.material_code,payload=json.dumps(study,ensure_ascii=False));db.add(row);db.commit();db.refresh(row)
    return {'id':row.id,**study,'diagnostics':diagnostics(study)}

@router.get('')
def listing(material_code:str,model_fingerprint:str='',db:Session=Depends(get_db)):
    result=[]
    for row in db.scalars(select(DoeRecord).where(DoeRecord.material_code==material_code).order_by(DoeRecord.id)):
        study=json.loads(row.payload)
        if model_fingerprint and study.get('model_fingerprint')!=model_fingerprint:continue
        result.append({'id':row.id,**study,'diagnostics':diagnostics(study)})
    return {'items':result}

@router.put('/{study_id}')
def save(study_id:str,p:Observations,db:Session=Depends(get_db)):
    row=db.get(DoeRecord,study_id)
    if not row:raise HTTPException(404,'DOE记录不存在')
    study=json.loads(row.payload)
    if len(p.values)!=study['runs'] or any(v is not None and (not np.isfinite(v) or abs(v)>1e15) for v in p.values):raise HTTPException(422,'响应数量须匹配试验次数，数值须有限且绝对值不超过1e15')
    if p.version!=study['version']:raise HTTPException(409,'DOE记录已更新，请重新加载')
    from sqlalchemy import update
    old=row.payload
    study.update(values=p.values,evidence=p.evidence,simulated=p.simulated,version=p.version+1)
    changed=db.execute(update(DoeRecord).where(DoeRecord.id==study_id,DoeRecord.payload==old).values(payload=json.dumps(study,ensure_ascii=False)))
    if changed.rowcount!=1:db.rollback();raise HTTPException(409,'记录已更新')
    db.commit()
    return {'id':row.id,**study,'diagnostics':diagnostics(study)}
