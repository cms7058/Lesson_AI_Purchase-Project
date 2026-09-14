import json
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.persistence import (
    NotificationOutboxRecord,
    WorkflowDefinitionRecord,
    WorkflowRunRecord,
)
from app.domain.workflows import Workflow, WorkflowCreate, WorkflowStep, WorkflowUpdate


def _workflow(record: WorkflowDefinitionRecord) -> Workflow:
    return Workflow(id=record.id, name=record.name, business_type=record.business_type, trigger_type=record.trigger_type, steps=[WorkflowStep.model_validate(item) for item in json.loads(record.steps_json)], status=record.status, created_by=record.created_by, created_at=record.created_at, updated_at=record.updated_at)


class WorkflowService:
    def _advance(
        self,
        db: Session,
        workflow: WorkflowDefinitionRecord,
        run: WorkflowRunRecord,
    ) -> None:
        definitions = json.loads(workflow.steps_json)
        result = json.loads(run.result_json)
        for index, step in enumerate(result["steps"]):
            if step["status"] != "pending":
                continue
            definition = definitions[index]
            if definition["action"] == "approval":
                step["status"] = "waiting"
                run.status = "awaiting_approval"
                break
            if definition["action"] == "email" and definition.get("recipient"):
                db.add(
                    NotificationOutboxRecord(
                        workflow_run_id=run.id,
                        recipient=definition["recipient"],
                        subject=definition.get("subject") or workflow.name,
                        body=(definition.get("content") or "工作流通知").replace(
                            "{{business_id}}", run.business_id
                        ),
                    )
                )
            step["status"] = "completed"
        else:
            run.status = "completed"
            run.finished_at = datetime.now(UTC)
        run.result_json = json.dumps(result, ensure_ascii=False)

    def list(self, db: Session, page: int, page_size: int) -> tuple[list[Workflow], int]:
        total=db.scalar(select(func.count()).select_from(WorkflowDefinitionRecord)) or 0
        records=db.scalars(select(WorkflowDefinitionRecord).order_by(WorkflowDefinitionRecord.created_at.desc()).offset((page-1)*page_size).limit(page_size))
        return [_workflow(item) for item in records],total

    def create(self,db:Session,payload:WorkflowCreate,user_id:str)->Workflow:
        item=WorkflowDefinitionRecord(name=payload.name,business_type=payload.business_type,trigger_type=payload.trigger_type,steps_json=json.dumps([step.model_dump(mode="json") for step in payload.steps],ensure_ascii=False),created_by=user_id)
        db.add(item);db.flush();db.refresh(item);return _workflow(item)

    def update(self,db:Session,item_id:str,payload:WorkflowUpdate)->Workflow|None:
        item=db.get(WorkflowDefinitionRecord,item_id)
        if item is None:return None
        values=payload.model_dump(exclude_none=True,exclude={"steps"})
        for key,value in values.items():setattr(item,key,value)
        if payload.steps is not None:item.steps_json=json.dumps([step.model_dump(mode="json") for step in payload.steps],ensure_ascii=False)
        db.flush();db.refresh(item);return _workflow(item)

    def execute(self,db:Session,item_id:str,business_id:str,user_id:str)->WorkflowRunRecord|None:
        workflow=db.get(WorkflowDefinitionRecord,item_id)
        if workflow is None or workflow.status != "active":return None
        steps=json.loads(workflow.steps_json)
        run=WorkflowRunRecord(workflow_id=workflow.id,workflow_name=workflow.name,business_id=business_id,status="running",result_json=json.dumps({"steps":[{"name":step["name"],"action":step["action"],"status":"pending"} for step in steps]},ensure_ascii=False),started_by=user_id)
        db.add(run);db.flush();self._advance(db,workflow,run);db.flush();return run

    def approve_run(self,db:Session,run_id:str)->WorkflowRunRecord|None:
        run=db.get(WorkflowRunRecord,run_id)
        if run is None:return None
        if run.status!="awaiting_approval":return run
        result=json.loads(run.result_json)
        waiting=next((step for step in result["steps"] if step["status"]=="waiting"),None)
        if waiting is not None:waiting["status"]="approved"
        run.result_json=json.dumps(result,ensure_ascii=False)
        workflow=db.get(WorkflowDefinitionRecord,run.workflow_id)
        if workflow is not None:self._advance(db,workflow,run)
        db.flush();return run

    def dispatch_email(self,db:Session,item_id:str)->tuple[NotificationOutboxRecord|None,str|None]:
        item=db.get(NotificationOutboxRecord,item_id)
        if item is None:return None,"not_found"
        settings=get_settings()
        if not settings.smtp_host or not settings.smtp_from_email:return None,"not_configured"
        message=EmailMessage();message["From"]=settings.smtp_from_email;message["To"]=item.recipient;message["Subject"]=item.subject;message.set_content(item.body)
        try:
            with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=15) as server:
                if settings.smtp_use_tls:server.starttls()
                if settings.smtp_username:server.login(settings.smtp_username,settings.smtp_password)
                server.send_message(message)
            item.status="sent";item.sent_at=datetime.now(UTC);item.error_message=""
        except (OSError, smtplib.SMTPException) as error:
            item.status="failed";item.error_message=str(error)[:1000]
            db.flush();return item,"send_failed"
        db.flush();return item,None


workflow_service=WorkflowService()
