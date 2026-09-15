import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.aviation_mro import (
    AviationMaterialProfile,
    AviationMaterialProfileRecord,
    AviationRequisitionProfile,
    AviationRequisitionProfileRecord,
    AviationSupplierCapability,
    AviationSupplierCapabilityRecord,
)
from app.domain.persistence import MaterialRecord, PurchaseRequisitionRecord, SupplierRecord
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/aviation-mro", tags=["aviation-mro"])
MANAGERS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}


@router.post("/demo")
def create_demo(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    require_manager(user)
    from app.seed_aviation_demo import seed

    result = seed(db)
    return {
        "result": result,
        "note": "仅新增带有【演示】或【公开资料参考】标识的数据，不代表真实商务关系",
    }


def require_manager(user: CurrentUser):
    if user.role not in MANAGERS:
        raise HTTPException(403, "当前角色无权维护航空MRO扩展数据")


def material_view(row):
    return {
        "material_code": row.material_code,
        "part_number": row.part_number,
        "oem": row.oem,
        "ata_chapter": row.ata_chapter,
        "applicability": row.applicability,
        "serial_controlled": row.serial_controlled,
        "batch_controlled": row.batch_controlled,
        "allowed_conditions": json.loads(row.allowed_conditions_json),
        "certificate_requirements": json.loads(row.certificate_requirements_json),
        "trace_required": row.trace_required,
        "shelf_life_days": row.shelf_life_days,
        "life_limited": row.life_limited,
        "minimum_remaining_life": row.minimum_remaining_life,
        "default_offer_type": row.default_offer_type,
        "note": row.note,
    }


@router.get("/materials/{material_code}")
def get_material_profile(material_code: str, db: Session = Depends(get_db)):
    row = db.get(AviationMaterialProfileRecord, material_code)
    return material_view(row) if row else None


@router.put("/materials/{material_code}")
def save_material_profile(
    material_code: str,
    payload: AviationMaterialProfile,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    require_manager(user)
    if not db.scalar(select(MaterialRecord.id).where(MaterialRecord.code == material_code)):
        raise HTTPException(404, "物料不存在")
    row = db.get(AviationMaterialProfileRecord, material_code)
    if not row:
        row = AviationMaterialProfileRecord(
            material_code=material_code, part_number=payload.part_number
        )
        db.add(row)
    values = payload.model_dump(exclude={"allowed_conditions", "certificate_requirements"})
    for key, value in values.items():
        setattr(row, key, value)
    row.allowed_conditions_json = json.dumps(payload.allowed_conditions, ensure_ascii=False)
    row.certificate_requirements_json = json.dumps(
        payload.certificate_requirements, ensure_ascii=False
    )
    write_audit_log(
        db,
        actor_id=user.user_id,
        actor_role=user.role,
        action="upsert",
        resource_type="aviation_material_profile",
        resource_id=material_code,
        detail=f"维护航空备件扩展档案 {payload.part_number}",
    )
    db.commit()
    db.refresh(row)
    return material_view(row)


def capability_view(row, supplier=None):
    return {
        "id": row.id,
        "supplier_id": row.supplier_id,
        "supplier_code": supplier.code if supplier else "",
        "supplier_name": supplier.name if supplier else "",
        "capability_name": row.capability_name,
        "supplier_type": row.supplier_type,
        "oem_scope": row.oem_scope,
        "part_scope": row.part_scope,
        "offer_types": json.loads(row.offer_types_json),
        "certificates": json.loads(row.certificates_json),
        "aog_247": row.aog_247,
        "response_hours": row.response_hours,
        "public_reference": row.public_reference,
        "relationship_status": row.relationship_status,
        "evidence": row.evidence,
        "version": row.version,
    }


@router.get("/supplier-capabilities")
def list_capabilities(
    supplier_id: str = "",
    keyword: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = []
    if supplier_id:
        filters.append(AviationSupplierCapabilityRecord.supplier_id == supplier_id)
    if keyword:
        term = f"%{keyword.strip()}%"
        filters.append(
            or_(
                AviationSupplierCapabilityRecord.capability_name.ilike(term),
                AviationSupplierCapabilityRecord.oem_scope.ilike(term),
                AviationSupplierCapabilityRecord.part_scope.ilike(term),
            )
        )
    total = (
        db.scalar(
            select(func.count()).select_from(AviationSupplierCapabilityRecord).where(*filters)
        )
        or 0
    )
    rows = list(
        db.scalars(
            select(AviationSupplierCapabilityRecord)
            .where(*filters)
            .order_by(AviationSupplierCapabilityRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    suppliers = (
        {
            x.id: x
            for x in db.scalars(
                select(SupplierRecord).where(SupplierRecord.id.in_([r.supplier_id for r in rows]))
            )
        }
        if rows
        else {}
    )
    return {
        "items": [capability_view(r, suppliers.get(r.supplier_id)) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/suppliers/{supplier_id}/capabilities", status_code=status.HTTP_201_CREATED)
def create_capability(
    supplier_id: str,
    payload: AviationSupplierCapability,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    require_manager(user)
    supplier = db.get(SupplierRecord, supplier_id)
    if not supplier:
        raise HTTPException(404, "供应商不存在")
    values = payload.model_dump(exclude={"offer_types", "certificates"})
    row = AviationSupplierCapabilityRecord(
        supplier_id=supplier_id,
        **values,
        offer_types_json=json.dumps(payload.offer_types, ensure_ascii=False),
        certificates_json=json.dumps(payload.certificates, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return capability_view(row, supplier)


@router.put("/requisitions/{requisition_id}")
def save_requisition_profile(
    requisition_id: str,
    payload: AviationRequisitionProfile,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    require_manager(user)
    if not db.get(PurchaseRequisitionRecord, requisition_id):
        raise HTTPException(404, "采购申请不存在")
    row = db.get(AviationRequisitionProfileRecord, requisition_id)
    if not row:
        row = AviationRequisitionProfileRecord(requisition_id=requisition_id)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return payload.model_dump() | {"requisition_id": requisition_id}


@router.get("/requisitions/{requisition_id}")
def get_requisition_profile(requisition_id: str, db: Session = Depends(get_db)):
    row = db.get(AviationRequisitionProfileRecord, requisition_id)
    if not row:
        return None
    return {key: getattr(row, key) for key in AviationRequisitionProfile.model_fields} | {
        "requisition_id": requisition_id
    }
