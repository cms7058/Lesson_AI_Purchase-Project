import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.persistence import (
    DemandForecastRecord,
    ProcurementReportRecord,
    RoutingPlanRecord,
    SourcingProjectRecord,
)
from app.domain.planning import (
    Forecast,
    ForecastCreate,
    ForecastUpdate,
    ProcurementReport,
    ReportCreate,
    ReportUpdate,
    RoutingCreate,
    RoutingPlan,
    RoutingUpdate,
    SourcingCreate,
    SourcingProject,
    SourcingUpdate,
)
from app.services.audit_service import write_audit_log
from app.services.planning_service import (
    _forecast,
    _optimize,
    _report,
    _routing,
    _sourcing,
    _sourcing_result,
    planning_service,
)

router=APIRouter(tags=["planning"])
EDIT_ROLES={UserRole.ADMIN,UserRole.PROCUREMENT_MANAGER,UserRole.BUYER,UserRole.ANALYST}


def _edit(user:CurrentUser)->None:
    if user.role not in EDIT_ROLES:raise HTTPException(status_code=403,detail="当前角色无权维护分析方案")


def _audit(db:Session,user:CurrentUser,action:str,kind:str,item_id:str,detail:str)->None:
    write_audit_log(db,actor_id=user.user_id,actor_role=user.role,action=action,resource_type=kind,resource_id=item_id,detail=detail)


@router.get("/forecasts",response_model=Page[Forecast])
def list_forecasts(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),keyword:str="",status:str="",db:Session=Depends(get_db)):
    records,total=planning_service.list_records(db,DemandForecastRecord,page,page_size,keyword,status);return Page(items=[_forecast(item) for item in records],page=page,page_size=page_size,total=total)


@router.post("/forecasts",response_model=Forecast,status_code=201)
def create_forecast(payload:ForecastCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);item=planning_service.create_forecast(db,payload,user.user_id);_audit(db,user,"create","forecast",str(item.id),f"创建需求预测 {item.name}");db.commit();return item


@router.patch("/forecasts/{item_id}",response_model=Forecast)
def update_forecast(item_id:str,payload:ForecastUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);record=db.get(DemandForecastRecord,item_id)
    if record is None:raise HTTPException(status_code=404,detail="未找到需求预测")
    item=planning_service.update_forecast(db,record,payload);_audit(db,user,"update","forecast",item_id,"更新并重新计算需求预测");db.commit();return item


@router.post("/forecasts/{item_id}/recalculate",response_model=Forecast)
def recalculate_forecast(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    return update_forecast(item_id,ForecastUpdate(),db,user)


@router.delete("/forecasts/{item_id}",status_code=204)
def delete_forecast(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);record=db.get(DemandForecastRecord,item_id)
    if record is None:raise HTTPException(status_code=404,detail="未找到需求预测")
    db.delete(record);_audit(db,user,"delete","forecast",item_id,"删除需求预测");db.commit()


@router.get("/sourcing-projects",response_model=Page[SourcingProject])
def list_sourcing(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),keyword:str="",status:str="",db:Session=Depends(get_db)):
    records,total=planning_service.list_records(db,SourcingProjectRecord,page,page_size,keyword,status);return Page(items=[_sourcing(item) for item in records],page=page,page_size=page_size,total=total)


@router.post("/sourcing-projects",response_model=SourcingProject,status_code=201)
def create_sourcing(payload:SourcingCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);item=planning_service.create_sourcing(db,payload,user.user_id);_audit(db,user,"create","sourcing",str(item.id),f"创建寻源项目 {item.name}");db.commit();return item


@router.patch("/sourcing-projects/{item_id}",response_model=SourcingProject)
def update_sourcing(item_id:str,payload:SourcingUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);record=db.get(SourcingProjectRecord,item_id)
    if record is None:raise HTTPException(status_code=404,detail="未找到寻源项目")
    item=planning_service.update_sourcing(db,record,payload);_audit(db,user,"update","sourcing",item_id,"更新寻源项目");db.commit();return item


@router.post("/sourcing-projects/{item_id}/evaluate",response_model=SourcingProject)
def evaluate_sourcing(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);record=db.get(SourcingProjectRecord,item_id)
    if record is None:raise HTTPException(status_code=404,detail="未找到寻源项目")
    candidates=json.loads(record.candidates_json)
    if not candidates:raise HTTPException(status_code=409,detail="请先录入外部候选供应商")
    record.result_json=json.dumps(_sourcing_result(candidates),ensure_ascii=False);record.status="evaluated";db.flush();item=_sourcing(record);_audit(db,user,"evaluate","sourcing",item_id,"完成候选供应商智能评价");db.commit();return item


@router.delete("/sourcing-projects/{item_id}",status_code=204)
def delete_sourcing(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit_delete(db,user,SourcingProjectRecord,item_id,"sourcing","寻源项目")


@router.get("/routing-plans",response_model=Page[RoutingPlan])
def list_routing(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),keyword:str="",status:str="",db:Session=Depends(get_db)):
    records,total=planning_service.list_records(db,RoutingPlanRecord,page,page_size,keyword,status);return Page(items=[_routing(item) for item in records],page=page,page_size=page_size,total=total)


@router.post("/routing-plans",response_model=RoutingPlan,status_code=201)
def create_routing(payload:RoutingCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);item=planning_service.create_routing(db,payload,user.user_id);_audit(db,user,"create","routing",str(item.id),f"创建路径方案 {item.name}");db.commit();return item


@router.patch("/routing-plans/{item_id}",response_model=RoutingPlan)
def update_routing(item_id:str,payload:RoutingUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);record=db.get(RoutingPlanRecord,item_id)
    if record is None:raise HTTPException(status_code=404,detail="未找到路径方案")
    item=planning_service.update_routing(db,record,payload);_audit(db,user,"update","routing",item_id,"更新路径方案");db.commit();return item


@router.post("/routing-plans/{item_id}/optimize",response_model=RoutingPlan)
def optimize_routing(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);record=db.get(RoutingPlanRecord,item_id)
    if record is None:raise HTTPException(status_code=404,detail="未找到路径方案")
    item=_routing(record);data=item.model_dump(mode="json",exclude={"id","result","status","created_by","created_at","updated_at","name","material_code"});result=_optimize(data);record.result_json=json.dumps(result,ensure_ascii=False);record.status="optimized" if result["feasible"] else "infeasible";db.flush();response=_routing(record);_audit(db,user,"optimize","routing",item_id,result["message"]);db.commit();return response


@router.delete("/routing-plans/{item_id}",status_code=204)
def delete_routing(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit_delete(db,user,RoutingPlanRecord,item_id,"routing","路径方案")


@router.get("/reports",response_model=Page[ProcurementReport])
def list_reports(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),keyword:str="",status:str="",db:Session=Depends(get_db)):
    records,total=planning_service.list_records(db,ProcurementReportRecord,page,page_size,keyword,status);return Page(items=[_report(item) for item in records],page=page,page_size=page_size,total=total)


@router.post("/reports",response_model=ProcurementReport,status_code=201)
def create_report(payload:ReportCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);record=ProcurementReportRecord(**payload.model_dump(),created_by=user.user_id);db.add(record);db.flush();item=_report(record);_audit(db,user,"create","report",str(item.id),f"创建报告 {item.title}");db.commit();return item


@router.patch("/reports/{item_id}",response_model=ProcurementReport)
def update_report(item_id:str,payload:ReportUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);record=db.get(ProcurementReportRecord,item_id)
    if record is None:raise HTTPException(status_code=404,detail="未找到报告")
    for key,value in payload.model_dump(exclude_none=True).items():setattr(record,key,value)
    record.status="draft";record.content_json="{}";db.flush();item=_report(record);_audit(db,user,"update","report",item_id,"更新报告定义");db.commit();return item


@router.post("/reports/{item_id}/generate",response_model=ProcurementReport)
def generate_report(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit(user);record=db.get(ProcurementReportRecord,item_id)
    if record is None:raise HTTPException(status_code=404,detail="未找到报告")
    item=planning_service.generate_report(db,record);_audit(db,user,"generate","report",item_id,"生成采购分析报告");db.commit();return item


@router.delete("/reports/{item_id}",status_code=204)
def delete_report(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _edit_delete(db,user,ProcurementReportRecord,item_id,"report","报告")


def _edit_delete(db:Session,user:CurrentUser,model,item_id:str,kind:str,label:str)->None:
    _edit(user);record=db.get(model,item_id)
    if record is None:raise HTTPException(status_code=404,detail=f"未找到{label}")
    db.delete(record);_audit(db,user,"delete",kind,item_id,f"删除{label}");db.commit()
