import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.persistence import (
    NotificationOutboxRecord,
    WorkflowDefinitionRecord,
    WorkflowRunRecord,
)
from app.domain.workflows import (
    NotificationOutbox,
    Workflow,
    WorkflowCreate,
    WorkflowExecute,
    WorkflowRun,
    WorkflowUpdate,
)
from app.services.audit_service import write_audit_log
from app.services.workflow_service import workflow_service

router=APIRouter(tags=["workflows"])


def _manager(user:CurrentUser)->None:
    if user.role not in {UserRole.ADMIN,UserRole.PROCUREMENT_MANAGER}:raise HTTPException(status_code=403,detail="当前角色无权管理自动化工作流")


def _run(item:WorkflowRunRecord)->WorkflowRun:
    return WorkflowRun(id=item.id,workflow_id=item.workflow_id,workflow_name=item.workflow_name,business_id=item.business_id,status=item.status,result=json.loads(item.result_json),started_by=item.started_by,started_at=item.started_at,finished_at=item.finished_at)


@router.get("/workflows",response_model=Page[Workflow])
def list_workflows(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    items,total=workflow_service.list(db,page,page_size);return Page(items=items,page=page,page_size=page_size,total=total)


@router.post("/workflows",response_model=Workflow,status_code=201)
def create_workflow(payload:WorkflowCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user)
    try:item=workflow_service.create(db,payload,user.user_id);db.flush()
    except IntegrityError as error:db.rollback();raise HTTPException(status_code=409,detail="工作流名称已存在") from error
    write_audit_log(db,actor_id=user.user_id,actor_role=user.role,action="create",resource_type="workflow",resource_id=str(item.id),detail=f"创建工作流 {item.name}");db.commit();return item


@router.patch("/workflows/{item_id}",response_model=Workflow)
def update_workflow(item_id:str,payload:WorkflowUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=workflow_service.update(db,item_id,payload)
    if item is None:raise HTTPException(status_code=404,detail="未找到工作流")
    write_audit_log(db,actor_id=user.user_id,actor_role=user.role,action="update",resource_type="workflow",resource_id=item_id,detail=f"更新工作流 {item.name}");db.commit();return item


@router.delete("/workflows/{item_id}",status_code=204)
def delete_workflow(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=db.get(WorkflowDefinitionRecord,item_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到工作流")
    db.delete(item);write_audit_log(db,actor_id=user.user_id,actor_role=user.role,action="delete",resource_type="workflow",resource_id=item_id,detail="删除工作流");db.commit()


@router.post("/workflows/{item_id}/execute",response_model=WorkflowRun,status_code=201)
def execute_workflow(item_id:str,payload:WorkflowExecute,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    definition=db.get(WorkflowDefinitionRecord,item_id)
    if definition is None:raise HTTPException(status_code=404,detail="未找到工作流")
    if definition.status!="active":raise HTTPException(status_code=409,detail="只有已启用的工作流可以运行")
    item=workflow_service.execute(db,item_id,payload.business_id,user.user_id)
    if item is None:raise HTTPException(status_code=409,detail="工作流无法运行")
    db.commit();db.refresh(item);return _run(item)


@router.get("/workflow-runs",response_model=Page[WorkflowRun])
def list_runs(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    total=db.scalar(select(func.count()).select_from(WorkflowRunRecord)) or 0;records=db.scalars(select(WorkflowRunRecord).order_by(WorkflowRunRecord.started_at.desc()).offset((page-1)*page_size).limit(page_size));return Page(items=[_run(item) for item in records],page=page,page_size=page_size,total=total)


@router.post("/workflow-runs/{run_id}/approve",response_model=WorkflowRun)
def approve_run(run_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=workflow_service.approve_run(db,run_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到工作流运行记录")
    db.commit();db.refresh(item);return _run(item)


@router.get("/notification-outbox",response_model=Page[NotificationOutbox])
def list_outbox(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    total=db.scalar(select(func.count()).select_from(NotificationOutboxRecord)) or 0;items=list(db.scalars(select(NotificationOutboxRecord).order_by(NotificationOutboxRecord.created_at.desc()).offset((page-1)*page_size).limit(page_size)));return Page(items=items,page=page,page_size=page_size,total=total)


@router.post("/notification-outbox/{item_id}/dispatch",response_model=NotificationOutbox)
def dispatch_email(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item,reason=workflow_service.dispatch_email(db,item_id)
    if reason=="not_found":raise HTTPException(status_code=404,detail="未找到邮件通知")
    if reason=="not_configured":raise HTTPException(status_code=409,detail="尚未配置 SMTP 服务")
    db.commit()
    if reason=="send_failed":raise HTTPException(status_code=502,detail=f"邮件发送失败：{item.error_message}")
    return item
