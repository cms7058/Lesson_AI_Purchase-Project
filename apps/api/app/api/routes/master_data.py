from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
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
from app.services.audit_service import write_audit_log
from app.services.master_data_service import master_data_service

router = APIRouter(tags=["master-data"])
MANAGERS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}


def _require_manager(user: CurrentUser) -> None:
    if user.role not in MANAGERS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权维护主数据")


def _audit(db: Session, user: CurrentUser, action: str, resource_type: str, resource_id: str, detail: str) -> None:
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action=action, resource_type=resource_type, resource_id=resource_id, detail=detail)


@router.get("/suppliers", response_model=Page[Supplier])
def list_suppliers(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = Query("", max_length=100), status_filter: str = Query("", alias="status"), db: Session = Depends(get_db)) -> Page[Supplier]:
    items, total = master_data_service.list_suppliers(db, page, page_size, keyword, status_filter)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post("/suppliers", response_model=Supplier, status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Supplier:
    _require_manager(user)
    item = master_data_service.create_supplier(db, payload, user.user_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="供应商编码已存在")
    _audit(db, user, "create", "supplier", str(item.id), f"创建供应商 {item.code} {item.name}")
    db.commit()
    return item


@router.patch("/suppliers/{item_id}", response_model=Supplier)
def update_supplier(item_id: str, payload: SupplierUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Supplier:
    _require_manager(user)
    item = master_data_service.update_supplier(db, item_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="未找到供应商")
    _audit(db, user, "update", "supplier", item_id, f"更新供应商 {item.code}")
    db.commit()
    return item


@router.delete("/suppliers/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    _require_manager(user)
    if not master_data_service.delete_supplier(db, item_id):
        raise HTTPException(status_code=404, detail="未找到供应商")
    _audit(db, user, "delete", "supplier", item_id, "删除供应商")
    db.commit()


@router.get("/materials", response_model=Page[Material])
def list_materials(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = Query("", max_length=100), material_type: str=Query('',pattern='^(|production|spare)$'), db: Session = Depends(get_db)) -> Page[Material]:
    items, total = master_data_service.list_materials(db, page, page_size, keyword,material_type)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post("/materials", response_model=Material, status_code=status.HTTP_201_CREATED)
def create_material(payload: MaterialCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Material:
    _require_manager(user)
    item = master_data_service.create_material(db, payload, user.user_id)
    if item is None:
        raise HTTPException(status_code=409, detail="物料编码已存在")
    _audit(db, user, "create", "material", str(item.id), f"创建物料 {item.code} {item.name}")
    db.commit()
    return item


@router.patch("/materials/{item_id}", response_model=Material)
def update_material(item_id: str, payload: MaterialUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Material:
    _require_manager(user)
    item = master_data_service.update_material(db, item_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="未找到物料")
    _audit(db, user, "update", "material", item_id, f"更新物料 {item.code}")
    db.commit()
    return item


@router.delete("/materials/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    _require_manager(user)
    if not master_data_service.delete_material(db, item_id):
        raise HTTPException(status_code=404, detail="未找到物料")
    _audit(db, user, "delete", "material", item_id, "删除物料")
    db.commit()


@router.get("/factories", response_model=Page[Factory])
def list_factories(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = Query("", max_length=100), db: Session = Depends(get_db)) -> Page[Factory]:
    items, total = master_data_service.list_factories(db, page, page_size, keyword)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.post("/factories", response_model=Factory, status_code=status.HTTP_201_CREATED)
def create_factory(payload: FactoryCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Factory:
    _require_manager(user)
    item = master_data_service.create_factory(db, payload, user.user_id)
    if item is None:
        raise HTTPException(status_code=409, detail="工厂编码已存在")
    _audit(db, user, "create", "factory", str(item.id), f"创建工厂 {item.code} {item.name}")
    db.commit()
    return item


@router.patch("/factories/{item_id}", response_model=Factory)
def update_factory(item_id: str, payload: FactoryUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Factory:
    _require_manager(user)
    item = master_data_service.update_factory(db, item_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="未找到工厂")
    _audit(db, user, "update", "factory", item_id, f"更新工厂 {item.code}")
    db.commit()
    return item


@router.delete("/factories/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_factory(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    _require_manager(user)
    if not master_data_service.delete_factory(db, item_id):
        raise HTTPException(status_code=404, detail="未找到工厂")
    _audit(db, user, "delete", "factory", item_id, "删除工厂")
    db.commit()
