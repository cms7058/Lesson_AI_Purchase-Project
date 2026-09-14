from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.persistence import (
    BusinessTemplateRecord,
    ContractRecord,
    DocumentTemplateLinkRecord,
    PurchaseOrderRecord,
    QuotationRecord,
)
from app.domain.template_links import DocumentType, TemplateLink, TemplateLinkCreate
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/template-links", tags=["template-links"])


@router.post("", response_model=TemplateLink, status_code=status.HTTP_201_CREATED)
def link_template(
    payload: TemplateLinkCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentTemplateLinkRecord:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权关联业务模板")
    template=db.get(BusinessTemplateRecord, str(payload.template_id))
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到业务模板")
    if template.template_type != payload.document_type or template.status != "active":
        raise HTTPException(status_code=409,detail="模板类型不匹配或模板未启用")
    record_type={"order":PurchaseOrderRecord,"quotation":QuotationRecord,"contract":ContractRecord}[payload.document_type]
    document=db.get(record_type,str(payload.document_id))
    if document is None:raise HTTPException(status_code=404,detail="未找到业务单据")
    for previous in db.scalars(select(DocumentTemplateLinkRecord).where(DocumentTemplateLinkRecord.document_type==payload.document_type,DocumentTemplateLinkRecord.document_id==str(payload.document_id))):
        db.delete(previous)
    if payload.document_type == DocumentType.ORDER:document.template_id=str(payload.template_id)
    link = DocumentTemplateLinkRecord(
        document_type=payload.document_type,
        document_id=str(payload.document_id),
        template_id=str(payload.template_id),
        created_by=current_user.user_id,
    )
    db.add(link)
    db.flush()
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="link", resource_type="template_link", resource_id=link.id, detail=f"关联{payload.document_type}与模板 {payload.template_id}")
    db.commit()
    db.refresh(link)
    return link
