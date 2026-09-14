from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class StepAction(StrEnum):
    APPROVAL = "approval"
    EMAIL = "email"
    UPDATE_STATUS = "update_status"
    CREATE_DOCUMENT = "create_document"
    WEBHOOK = "webhook"


class WorkflowStep(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    action: StepAction
    recipient: str | None = Field(default=None, max_length=200)
    subject: str = Field(default="", max_length=300)
    content: str = Field(default="", max_length=3000)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    business_type: str = Field(pattern="^(quotation|order|contract|requisition|payment)$")
    trigger_type: str = Field(default="manual", pattern="^(manual|status_change|scheduled)$")
    steps: list[WorkflowStep] = Field(min_length=1)


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    business_type: str | None = Field(default=None, pattern="^(quotation|order|contract|requisition|payment)$")
    trigger_type: str | None = Field(default=None, pattern="^(manual|status_change|scheduled)$")
    steps: list[WorkflowStep] | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern="^(draft|active|disabled)$")


class Workflow(WorkflowCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class WorkflowExecute(BaseModel):
    business_id: str = Field(default="", max_length=64)


class WorkflowRun(BaseModel):
    id: UUID
    workflow_id: UUID
    workflow_name: str
    business_id: str
    status: str
    result: dict
    started_by: str
    started_at: datetime
    finished_at: datetime | None


class NotificationOutbox(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workflow_run_id: UUID
    channel: str
    recipient: str
    subject: str
    body: str
    status: str
    error_message: str
    created_at: datetime
    sent_at: datetime | None
