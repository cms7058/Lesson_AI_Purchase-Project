from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.organization import BuyerAuthorization, SupplierCategoryLink
from app.domain.persistence import (
    BuyerCategoryAuthorizationRecord,
    MaterialCategoryRecord,
    StaffUserRecord,
    SupplierCategoryLinkRecord,
    SupplierRecord,
)


class OrganizationService:
    def next_category_code(self, db: Session, parent: MaterialCategoryRecord | None, code_segment: str | None = None) -> tuple[str, int, str]:
        level = 1 if parent is None else parent.level + 1
        if level > 3:
            raise ValueError("物料分类最多支持三级")
        if code_segment:
            segment = code_segment.upper()
            return (segment if parent is None else f"{parent.code}-{segment}"), level, parent.path_name if parent else ""
        parent_id = None if parent is None else parent.id
        siblings = list(db.scalars(select(MaterialCategoryRecord).where(MaterialCategoryRecord.parent_id == parent_id)))
        used = {int(item.code.split("-")[-1]) for item in siblings if item.code.split("-")[-1].isdigit()}
        sequence = next((value for value in range(1, 100) if value not in used), None)
        if sequence is None:
            raise ValueError("当前层级分类编号已用完")
        segment = f"{sequence:02d}"
        code = segment if parent is None else f"{parent.code}-{segment}"
        return code, level, parent.path_name if parent else ""

    def list_records(self, db: Session, model, page: int, page_size: int, keyword: str = "", status: str = ""):
        query = select(model)
        if keyword:
            pattern = f"%{keyword}%"
            if model is MaterialCategoryRecord:
                query = query.where(or_(model.code.ilike(pattern), model.name.ilike(pattern), model.path_name.ilike(pattern)))
            else:
                query = query.where(or_(model.user_code.ilike(pattern), model.name.ilike(pattern), model.department.ilike(pattern)))
        if status:
            query = query.where(model.status == status)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        return list(db.scalars(query.order_by(model.created_at.desc()).offset((page - 1) * page_size).limit(page_size))), total

    def authorization(self, db: Session, item: BuyerCategoryAuthorizationRecord) -> BuyerAuthorization:
        buyer = db.get(StaffUserRecord, item.buyer_id); category = db.get(MaterialCategoryRecord, item.category_id)
        today = datetime.now(UTC).date()
        return BuyerAuthorization(id=item.id,buyer_id=item.buyer_id,buyer_name=buyer.name if buyer else "已删除人员",category_id=item.category_id,category_code=category.code if category else "",category_name=category.path_name if category else "已删除分类",category_level=category.level if category else 0,valid_from=item.valid_from,valid_to=item.valid_to,status=item.status,effective=bool(buyer and buyer.status=="active" and buyer.role=="buyer" and category and category.active and item.status=="active" and item.valid_from<=today<=item.valid_to),created_at=item.created_at)

    def supplier_link(self, db: Session, item: SupplierCategoryLinkRecord) -> SupplierCategoryLink:
        supplier=db.get(SupplierRecord,item.supplier_id);category=db.get(MaterialCategoryRecord,item.category_id)
        return SupplierCategoryLink(id=item.id,supplier_id=item.supplier_id,supplier_code=supplier.code if supplier else "",supplier_name=supplier.name if supplier else "已删除供应商",category_id=item.category_id,category_code=category.code if category else "",category_name=category.path_name if category else "已删除分类",category_level=category.level if category else 0,qualification_status=item.qualification_status,created_at=item.created_at)


organization_service=OrganizationService()
