from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.persistence import ComparisonSnapshotRecord
from app.domain.quotations import BidComparison, Quotation, QuotationCreate, QuotationUpdate
from app.services.audit_service import write_audit_log
from app.services.quotation_service import quotation_service

router = APIRouter(prefix="/quotations", tags=["quotations"])


@router.get("", response_model=Page[Quotation])
def list_quotations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Page[Quotation]:
    items, total = quotation_service.list_quotations(db, page, page_size)
    return Page(items=list(items), page=page, page_size=page_size, total=total)


@router.post("", response_model=Quotation, status_code=status.HTTP_201_CREATED)
def create_quotation(
    payload: QuotationCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Quotation:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权录入报价")
    quotation = quotation_service.create_quotation(db, payload, current_user.user_id)
    write_audit_log(
        db,
        actor_id=current_user.user_id,
        actor_role=current_user.role,
        action="create",
        resource_type="quotation",
        resource_id=str(quotation.id),
        detail=f"录入报价 {quotation.quotation_no}，来源：{quotation.source_type}",
    )
    db.commit()
    return quotation


@router.patch("/{quotation_id}", response_model=Quotation)
def update_quotation(
    quotation_id: str,
    payload: QuotationUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Quotation:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权修改报价")
    quotation = quotation_service.update_quotation(db, quotation_id, payload, current_user.user_id)
    if quotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到报价")
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="update", resource_type="quotation", resource_id=quotation_id, detail=f"更新报价 {quotation.quotation_no}")
    db.commit()
    return quotation


@router.delete("/{quotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quotation(
    quotation_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    if current_user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权删除报价")
    if not quotation_service.delete_quotation(db, quotation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到报价")
    write_audit_log(db, actor_id=current_user.user_id, actor_role=current_user.role, action="delete", resource_type="quotation", resource_id=quotation_id, detail="删除报价")
    db.commit()


@router.get("/compare", response_model=BidComparison)
def compare_quotations(
    material_code: str = Query(min_length=1, max_length=64),
    quantity: Decimal = Query(gt=0),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> BidComparison:
    try:
        result = quotation_service.compare(db, material_code, quantity, currency)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if result.items:
        db.add(ComparisonSnapshotRecord(material_code=material_code,currency=result.currency,quantity=quantity,result_json=result.model_dump_json(),created_by=current_user.user_id))
    write_audit_log(
        db,
        actor_id=current_user.user_id,
        actor_role=current_user.role,
        action="compare",
        resource_type="quotation",
        resource_id=material_code,
        detail=f"比价物料 {material_code}，数量 {quantity}",
    )
    db.commit()
    return result
