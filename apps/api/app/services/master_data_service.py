import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.equipment_mro import EquipmentBomRecord, EquipmentRecord
from app.domain.master_data import (
    Factory,
    FactoryCreate,
    FactoryUpdate,
    Material,
    MaterialCreate,
    MaterialUpdate,
    Supplier,
    SupplierCreate,
    SupplierUpdate,
)
from app.domain.material_documents import MaterialTechnicalDocumentRecord
from app.domain.material_policy import MaterialPolicy, SpareClassification
from app.domain.persistence import (
    ContractRecord,
    FactoryRecord,
    MaterialCategoryAssignmentRecord,
    MaterialRecord,
    PurchaseOrderLineRecord,
    PurchaseOrderRecord,
    PurchaseRequisitionLineRecord,
    PurchaseRequisitionRecord,
    QuotationLineRecord,
    QuotationRecord,
    RFQInvitationRecord,
    RFQLineRecord,
    SupplierCategoryLinkRecord,
    SupplierRecord,
)
from app.domain.supplier_qualifications import SupplierQualificationRecord
from app.domain.supply_feedback import SupplyFeedback
from app.services.references import protect_references


def _values(payload) -> dict:
    return {
        key: value.value if hasattr(value, "value") else value
        for key, value in payload.model_dump(exclude_none=True).items()
    }


class MasterDataService:
    def list_suppliers(self, db: Session, page: int, page_size: int, keyword: str = "", status: str = "") -> tuple[list[Supplier], int]:
        filters = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(SupplierRecord.code.ilike(pattern), SupplierRecord.name.ilike(pattern), SupplierRecord.category.ilike(pattern)))
        if status:
            filters.append(SupplierRecord.status == status)
        total = db.scalar(select(func.count()).select_from(SupplierRecord).where(*filters)) or 0
        records = db.scalars(select(SupplierRecord).where(*filters).order_by(SupplierRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        return [Supplier.model_validate(record) for record in records], total

    def create_supplier(self, db: Session, payload: SupplierCreate, created_by: str) -> Supplier | None:
        if db.scalar(select(SupplierRecord.id).where(SupplierRecord.code == payload.code.strip())):
            return None
        values = _values(payload)
        values["code"] = payload.code.strip()
        record = SupplierRecord(**values, created_by=created_by)
        db.add(record); db.flush(); db.refresh(record)
        return Supplier.model_validate(record)

    def update_supplier(self, db: Session, item_id: str, payload: SupplierUpdate) -> Supplier | None:
        record = db.get(SupplierRecord, item_id)
        if record is None:
            return None
        for key, value in _values(payload).items():
            setattr(record, key, value)
        db.flush(); db.refresh(record)
        return Supplier.model_validate(record)

    def delete_supplier(self, db: Session, item_id: str) -> bool:
        record = db.get(SupplierRecord, item_id)
        if record is None:
            return False
        ids=[record.id,record.code]
        protect_references(db, [(SupplyFeedback, SupplyFeedback.supplier_code == record.code)], "供应商供货反馈")
        protect_references(db, [(SupplierQualificationRecord, SupplierQualificationRecord.supplier_id == record.id)], "供应商资质")
        protect_references(db, [(PurchaseOrderRecord, PurchaseOrderRecord.supplier_id.in_(ids)), (QuotationRecord, QuotationRecord.supplier_id.in_(ids)), (ContractRecord, ContractRecord.supplier_id.in_(ids)), (RFQInvitationRecord, RFQInvitationRecord.supplier_id.in_(ids))], "供应商")
        links = db.scalars(select(SupplierCategoryLinkRecord).where(SupplierCategoryLinkRecord.supplier_id == item_id))
        for link in links:
            db.delete(link)
        db.delete(record)
        return True

    def list_materials(self, db: Session, page: int, page_size: int, keyword: str = "", material_type: str = "") -> tuple[list[Material], int]:
        filters = []
        if material_type:
            spare_codes=[p.material_code for p in db.scalars(select(MaterialPolicy)) if json.loads(p.payload).get('material_type')=='spare']
            filters.append(MaterialRecord.code.in_(spare_codes) if material_type=='spare' else MaterialRecord.code.not_in(spare_codes))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(MaterialRecord.code.ilike(pattern), MaterialRecord.name.ilike(pattern), MaterialRecord.specification.ilike(pattern)))
        total = db.scalar(select(func.count()).select_from(MaterialRecord).where(*filters)) or 0
        records = db.scalars(select(MaterialRecord).where(*filters).order_by(MaterialRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        return [self.material_view(db,record) for record in records], total

    def material_view(self,db,record):
        policy=db.get(MaterialPolicy,record.code)
        return Material.model_validate(record).model_copy(update={'spare_classification':SpareClassification.model_validate_json(policy.payload) if policy else SpareClassification()})

    def create_material(self, db: Session, payload: MaterialCreate, created_by: str) -> Material | None:
        if db.scalar(select(MaterialRecord.id).where(MaterialRecord.code == payload.code.strip())):
            return None
        values = _values(payload)
        values["code"] = payload.code.strip()
        policy=values.pop('spare_classification')
        record = MaterialRecord(**values, created_by=created_by)
        db.add(record); db.flush(); db.refresh(record)
        db.add(MaterialPolicy(material_code=record.code,payload=json.dumps(policy,ensure_ascii=False)));db.flush()
        return self.material_view(db,record)

    def update_material(self, db: Session, item_id: str, payload: MaterialUpdate) -> Material | None:
        record = db.get(MaterialRecord, item_id)
        if record is None:
            return None
        values=_values(payload)
        classification=values.pop('spare_classification',None)
        if classification is not None:
            policy=db.get(MaterialPolicy,record.code)
            if not policy:
                policy=MaterialPolicy(material_code=record.code);db.add(policy)
            policy.payload=json.dumps(classification,ensure_ascii=False)
        for key, value in values.items():
            setattr(record, key, value)
        db.flush(); db.refresh(record)
        return self.material_view(db,record)

    def delete_material(self, db: Session, item_id: str) -> bool:
        record = db.get(MaterialRecord, item_id)
        if record is None:
            return False
        protect_references(db, [(SupplyFeedback, SupplyFeedback.material_code == record.code)], "物料供货反馈")
        protect_references(db, [(MaterialTechnicalDocumentRecord, MaterialTechnicalDocumentRecord.material_id == record.id)], "物料技术资料")
        protect_references(db, [(EquipmentBomRecord, EquipmentBomRecord.material_id == record.id)], "设备BOM")
        protect_references(db, [(PurchaseOrderLineRecord, PurchaseOrderLineRecord.material_code == record.code), (QuotationLineRecord, QuotationLineRecord.material_code == record.code), (PurchaseRequisitionLineRecord, PurchaseRequisitionLineRecord.material_code == record.code), (RFQLineRecord, RFQLineRecord.material_code == record.code)], "物料")
        assignment = db.scalar(select(MaterialCategoryAssignmentRecord).where(MaterialCategoryAssignmentRecord.material_id == item_id))
        if assignment:
            db.delete(assignment)
        policy=db.get(MaterialPolicy,record.code)
        if policy:db.delete(policy)
        db.delete(record)
        return True

    def list_factories(self, db: Session, page: int, page_size: int, keyword: str = "") -> tuple[list[Factory], int]:
        filters = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(FactoryRecord.code.ilike(pattern), FactoryRecord.name.ilike(pattern), FactoryRecord.address.ilike(pattern)))
        total = db.scalar(select(func.count()).select_from(FactoryRecord).where(*filters)) or 0
        records = db.scalars(select(FactoryRecord).where(*filters).order_by(FactoryRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        return [Factory.model_validate(record) for record in records], total

    def create_factory(self, db: Session, payload: FactoryCreate, created_by: str) -> Factory | None:
        if db.scalar(select(FactoryRecord.id).where(FactoryRecord.code == payload.code.strip())):
            return None
        values = _values(payload)
        values["code"] = payload.code.strip()
        record = FactoryRecord(**values, created_by=created_by)
        db.add(record); db.flush(); db.refresh(record)
        return Factory.model_validate(record)

    def update_factory(self, db: Session, item_id: str, payload: FactoryUpdate) -> Factory | None:
        record = db.get(FactoryRecord, item_id)
        if record is None:
            return None
        for key, value in _values(payload).items():
            setattr(record, key, value)
        db.flush(); db.refresh(record)
        return Factory.model_validate(record)

    def delete_factory(self, db: Session, item_id: str) -> bool:
        record = db.get(FactoryRecord, item_id)
        if record is None:
            return False
        protect_references(db, [(EquipmentRecord, EquipmentRecord.factory_code == record.code)], "设备台账")
        protect_references(db, [(PurchaseOrderRecord, PurchaseOrderRecord.factory_code == record.code), (PurchaseRequisitionRecord, PurchaseRequisitionRecord.factory_code == record.code)], "工厂")
        db.delete(record)
        return True


master_data_service = MasterDataService()
