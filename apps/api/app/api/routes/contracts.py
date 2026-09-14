from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.contract_reviews import ContractDocumentRecord, ContractReviewRecord
from app.domain.contracts import Contract, ContractCreate, ContractDecision, ContractUpdate
from app.domain.persistence import (
    BusinessTemplateRecord,
    ContractRecord,
    DocumentTemplateLinkRecord,
)
from app.domain.template_links import DocumentType
from app.services.audit_service import write_audit_log
from app.services.contract_service import contract_service

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("", response_model=Page[Contract])
def list_contracts(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), keyword: str = Query(default="", max_length=100), contract_status: str = Query(default="", alias="status", pattern="^(|draft|pending_approval|active|expired|terminated)$"), db: Session = Depends(get_db)) -> Page[Contract]:
    items, total = contract_service.list_contracts(db, page, page_size, keyword, contract_status)
    return Page(items=list(items), page=page, page_size=page_size, total=total)


@router.post("", response_model=Contract, status_code=status.HTTP_201_CREATED)
def create_contract(payload: ContractCreate, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> Contract:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权创建合同")
    if payload.template_id:
        template = db.get(BusinessTemplateRecord, str(payload.template_id))
        if template is None or template.template_type != "contract":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到合同模板")
    contract = contract_service.create_contract(db, payload, current_user.user_id)
    if payload.template_id:
        db.add(DocumentTemplateLinkRecord(document_type=DocumentType.CONTRACT, document_id=str(contract.id), template_id=str(payload.template_id), created_by=current_user.user_id))
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="create", resource_type="contract", resource_id=str(contract.id), detail=f"创建合同 {contract.contract_no}")
    db.commit()
    return contract


@router.patch("/{contract_id}", response_model=Contract)
def update_contract(contract_id: str, payload: ContractUpdate, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> Contract:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权修改合同")
    existing = db.get(ContractRecord, contract_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到合同")
    if existing.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿合同可以修改")
    if payload.template_id:
        template = db.get(BusinessTemplateRecord, str(payload.template_id))
        if template is None or template.template_type != "contract":
            raise HTTPException(status_code=404, detail="未找到合同模板")
    contract = contract_service.update_contract(db, contract_id, payload)
    if "template_id" in payload.model_fields_set:
        links = db.query(DocumentTemplateLinkRecord).filter_by(document_type=DocumentType.CONTRACT, document_id=contract_id).all()
        for link in links:
            db.delete(link)
        if payload.template_id:
            db.add(DocumentTemplateLinkRecord(document_type=DocumentType.CONTRACT, document_id=contract_id, template_id=str(payload.template_id), created_by=current_user.user_id))
        db.flush()
        contract = contract_service.update_contract(db, contract_id, ContractUpdate())
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="update", resource_type="contract", resource_id=contract_id, detail=f"更新合同 {contract.contract_no}")
    db.commit()
    return contract


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(contract_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> None:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权删除合同")
    existing = db.get(ContractRecord, contract_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到合同")
    if existing.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿合同可以删除")
    contract_service.delete_contract(db, contract_id)
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="delete", resource_type="contract", resource_id=contract_id, detail="删除合同")
    db.commit()


@router.post("/{contract_id}/submit", response_model=Contract)
def submit_contract(contract_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> Contract:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(status_code=403, detail="当前角色无权提交合同")
    latest_document = db.scalars(select(ContractDocumentRecord).where(ContractDocumentRecord.contract_id == contract_id).order_by(ContractDocumentRecord.version.desc()).limit(1)).first()
    if latest_document:
        reviewed = db.scalar(select(func.count()).select_from(ContractReviewRecord).where(ContractReviewRecord.document_id == latest_document.id)) or 0
        if not reviewed:
            raise HTTPException(status_code=409, detail="最新合同文件尚未完成AI审查，请审查后再提交")
    contract = contract_service.transition(db, contract_id, "draft", "pending_approval")
    if contract is None:
        raise HTTPException(status_code=409, detail="只有草稿合同可以提交审批")
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="submit", resource_type="contract", resource_id=contract_id, detail="提交合同审批")
    db.commit()
    return contract


@router.post("/{contract_id}/decision", response_model=Contract)
def decide_contract(contract_id: str, payload: ContractDecision, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> Contract:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=403, detail="当前角色无权审批合同")
    contract = contract_service.transition(db, contract_id, "pending_approval", "active" if payload.approved else "draft")
    if contract is None:
        raise HTTPException(status_code=409, detail="只有待审批合同可以审批")
    action = "approve" if payload.approved else "reject"
    detail = payload.comment or ("合同审批通过" if payload.approved else "合同审批驳回")
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action=action, resource_type="contract", resource_id=contract_id, detail=detail)
    db.commit()
    return contract


@router.post("/{contract_id}/terminate", response_model=Contract)
def terminate_contract(contract_id: str, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)) -> Contract:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=403, detail="当前角色无权终止合同")
    contract = contract_service.transition(db, contract_id, "active", "terminated")
    if contract is None:
        raise HTTPException(status_code=409, detail="只有履约中的合同可以终止")
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="terminate", resource_type="contract", resource_id=contract_id, detail="终止合同履约")
    db.commit()
    return contract
