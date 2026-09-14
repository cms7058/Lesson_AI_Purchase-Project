from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.persistence import GeneratedBusinessDocumentRecord
from app.services.audit_service import write_audit_log
from app.services.document_export_service import document_export_service

router = APIRouter(prefix="/documents", tags=["documents"])


class ExportRequest(BaseModel):
    template_id: str
    output_format: Literal["docx", "pdf"]


class ExportResult(BaseModel):
    file_name: str
    download_url: str


class PreflightResult(BaseModel):
    valid: bool
    template_id: str
    template_name: str
    template_version: str
    engine: str
    validation_status: str
    placeholders: list[str]
    unresolved: list[str]
    missing_required: list[str]
    warnings: list[str]
    pdf_available: bool


class GeneratedDocumentItem(BaseModel):
    id: str
    template_id: str
    template_version: str
    output_format: str
    file_name: str
    download_url: str
    sha256: str
    created_by: str
    created_at: datetime


@router.get("/contract/{contract_id}/preflight", response_model=PreflightResult)
def contract_preflight(contract_id: str, template_id: str, db: Session = Depends(get_db)) -> PreflightResult:
    try:
        return PreflightResult(**document_export_service.preflight(db, "contract", contract_id, template_id))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/contract/{contract_id}/history", response_model=list[GeneratedDocumentItem])
def contract_document_history(contract_id: str, db: Session = Depends(get_db)) -> list[GeneratedDocumentItem]:
    records = db.scalars(
        select(GeneratedBusinessDocumentRecord)
        .where(GeneratedBusinessDocumentRecord.source_type == "contract", GeneratedBusinessDocumentRecord.source_id == contract_id)
        .order_by(GeneratedBusinessDocumentRecord.created_at.desc())
    )
    return [GeneratedDocumentItem(
        id=item.id, template_id=item.template_id, template_version=item.template_version,
        output_format=item.output_format, file_name=item.file_name,
        download_url=f"/files/documents/{item.file_name}", sha256=item.sha256,
        created_by=item.created_by, created_at=item.created_at,
    ) for item in records]


@router.post("/{source_type}/{source_id}/export", response_model=ExportResult)
def export_document(source_type: Literal["order", "quotation", "contract"], source_id: str, payload: ExportRequest, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> ExportResult:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(status_code=403, detail="当前角色无权生成业务单据")
    try:
        file_name, download_url = document_export_service.export(db, source_type, source_id, payload.template_id, payload.output_format, current_user.user_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="export", resource_type=source_type, resource_id=source_id, detail=f"导出{payload.output_format}单据")
    db.commit()
    return ExportResult(file_name=file_name, download_url=download_url)
