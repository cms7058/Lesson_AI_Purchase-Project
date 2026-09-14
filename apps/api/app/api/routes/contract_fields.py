import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.contract_fields import ContractField, ContractFieldCreate, ContractFieldUpdate
from app.domain.persistence import ContractFieldDefinitionRecord, ManagedWordTemplateRecord
from app.domain.templates import BusinessTemplate
from app.services.audit_service import write_audit_log
from app.services.template_service import template_service
from app.services.word_template_service import (
    build_managed_contract_template,
    create_word_template,
    revalidate_all_word_templates,
    sync_managed_word_templates,
)

router = APIRouter(prefix="/contract-fields", tags=["contract-fields"])


class ManagedTemplateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    version: str = Field(default="1.0", min_length=1, max_length=24)
    field_ids: list[str] = Field(default_factory=list)


def _manager(user: CurrentUser) -> None:
    if user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=403, detail="当前角色无权管理合同字段")


def _domain(record: ContractFieldDefinitionRecord) -> ContractField:
    return ContractField(
        id=record.id, code=record.code, name=record.name, category=record.category,
        data_type=record.data_type, required=record.required, active=record.active,
        default_value=record.default_value, options=json.loads(record.options_json or "[]"),
        source_path=record.source_path, sort_order=record.sort_order,
        created_by=record.created_by, created_at=record.created_at,
    )


@router.get("", response_model=Page[ContractField])
def list_contract_fields(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
    keyword: str = Query(default="", max_length=100), active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Page[ContractField]:
    query = select(ContractFieldDefinitionRecord)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.where(or_(ContractFieldDefinitionRecord.code.ilike(pattern), ContractFieldDefinitionRecord.name.ilike(pattern)))
    if active is not None:
        query = query.where(ContractFieldDefinitionRecord.active.is_(active))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.order_by(ContractFieldDefinitionRecord.sort_order, ContractFieldDefinitionRecord.created_at).offset((page - 1) * page_size).limit(page_size))
    return Page(items=[_domain(item) for item in records], page=page, page_size=page_size, total=total)


@router.post("", response_model=ContractField, status_code=status.HTTP_201_CREATED)
def create_contract_field(payload: ContractFieldCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> ContractField:
    _manager(user)
    record = ContractFieldDefinitionRecord(
        **payload.model_dump(exclude={"options"}), options_json=json.dumps(payload.options, ensure_ascii=False), created_by=user.user_id,
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="字段编码已存在") from error
    sync_managed_word_templates(db)
    revalidate_all_word_templates(db)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="create", resource_type="contract_field", resource_id=record.id, detail=f"创建合同字段 {record.code}")
    db.commit(); db.refresh(record)
    return _domain(record)


@router.post("/generate-template", response_model=BusinessTemplate, status_code=status.HTTP_201_CREATED)
def generate_managed_contract_template(payload: ManagedTemplateRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> BusinessTemplate:
    _manager(user)
    query = select(ContractFieldDefinitionRecord).where(ContractFieldDefinitionRecord.active.is_(True))
    if payload.field_ids:
        query = query.where(ContractFieldDefinitionRecord.id.in_(payload.field_ids))
    fields = list(db.scalars(query.order_by(ContractFieldDefinitionRecord.sort_order)))
    template_record = create_word_template(
        db,
        name=payload.name,
        version=payload.version,
        data=build_managed_contract_template(fields),
        filename=f"{payload.name}.docx",
        created_by=user.user_id,
    )
    db.add(ManagedWordTemplateRecord(template_id=template_record.id, field_ids_json=json.dumps(payload.field_ids, ensure_ascii=False)))
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="generate", resource_type="business_template", resource_id=template_record.id, detail=f"按合同字段配置生成模板 {template_record.name}")
    db.commit()
    result = template_service.get_template(db, template_record.id)
    assert result is not None
    return result


@router.patch("/{field_id}", response_model=ContractField)
def update_contract_field(field_id: str, payload: ContractFieldUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> ContractField:
    _manager(user)
    record = db.get(ContractFieldDefinitionRecord, field_id)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到合同字段")
    values = payload.model_dump(exclude_none=True, exclude={"options"})
    for key, value in values.items():
        setattr(record, key, value)
    if payload.options is not None:
        record.options_json = json.dumps(payload.options, ensure_ascii=False)
    sync_managed_word_templates(db)
    revalidate_all_word_templates(db)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="update", resource_type="contract_field", resource_id=record.id, detail=f"更新合同字段 {record.code}")
    db.commit(); db.refresh(record)
    return _domain(record)


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_contract_field(field_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    _manager(user)
    record = db.get(ContractFieldDefinitionRecord, field_id)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到合同字段")
    record.active = False
    sync_managed_word_templates(db)
    revalidate_all_word_templates(db)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="deactivate", resource_type="contract_field", resource_id=record.id, detail=f"停用合同字段 {record.code}")
    db.commit()
