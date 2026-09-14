
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.common import Page
from app.domain.order_buyer import OrderBuyerAssignment
from app.domain.organization import (
    BuyerAuthorization,
    BuyerAuthorizationCreate,
    BuyerAuthorizationUpdate,
    CategoryCreate,
    CategoryUpdate,
    MaterialAssignment,
    MaterialCategory,
    StaffCreate,
    StaffUpdate,
    StaffUser,
    SupplierCategoryLink,
    SupplierCategoryLinkCreate,
    SupplierCategoryLinkUpdate,
)
from app.domain.persistence import (
    BuyerCategoryAuthorizationRecord,
    MaterialCategoryAssignmentRecord,
    MaterialCategoryRecord,
    MaterialRecord,
    StaffUserRecord,
    SupplierCategoryLinkRecord,
    SupplierRecord,
)
from app.services.audit_service import write_audit_log
from app.services.category_templates import TEMPLATES, template_rows
from app.services.organization_service import organization_service

router=APIRouter(tags=["organization"])
MANAGERS={UserRole.ADMIN,UserRole.PROCUREMENT_MANAGER}


@router.get("/material-categories/industry-templates/{industry}")
def preview_industry(industry: str):
    if industry not in TEMPLATES:raise HTTPException(status_code=404,detail="未找到行业模板")
    return {"name": TEMPLATES[industry]["name"], "items": template_rows(industry), "note": "通用起步分类，可按企业需求调整；不是官方行业标准。不创建虚构物料档案。"}


@router.post("/material-categories/import/{industry}")
def import_industry(industry: str, db: Session=Depends(get_db), user: CurrentUser=Depends(get_current_user)):
    _manager(user)
    if industry not in TEMPLATES:raise HTTPException(status_code=404,detail="未找到行业模板")
    existing={item.code:item for item in db.scalars(select(MaterialCategoryRecord))}
    created=0
    for row in template_rows(industry):
        parent=existing.get(row["parent_code"])
        item=existing.get(row["code"])
        if item:
            if item.name!=row["name"] or item.parent_id!=(parent.id if parent else None):
                raise HTTPException(status_code=409,detail=f"编码 {row['code']} 与现有分类冲突，未导入任何内容")
            continue
        item=MaterialCategoryRecord(code=row["code"],name=row["name"],level=row["level"],parent_id=parent.id if parent else None,path_name=f"{parent.path_name} / {row['name']}" if parent else row["name"],created_by=user.user_id)
        db.add(item);db.flush();existing[item.code]=item;created+=1
    _audit(db,user,"import","material_category",industry,f"导入行业分类：新增 {created} 项")
    db.commit()
    return {"created":created,"skipped":len(template_rows(industry))-created}


def _manager(user:CurrentUser)->None:
    if user.role not in MANAGERS:raise HTTPException(status_code=403,detail="当前角色无权维护组织与分类权限")


def _audit(db:Session,user:CurrentUser,action:str,kind:str,item_id:str,detail:str)->None:
    write_audit_log(db,actor_id=user.user_id,actor_role=user.role,action=action,resource_type=kind,resource_id=item_id,detail=detail)


@router.get("/material-categories",response_model=Page[MaterialCategory])
def list_categories(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),keyword:str="",level:int|None=Query(None,ge=1,le=3),db:Session=Depends(get_db)):
    query=select(MaterialCategoryRecord)
    if keyword:
        pattern=f"%{keyword}%";query=query.where((MaterialCategoryRecord.code.ilike(pattern))|(MaterialCategoryRecord.path_name.ilike(pattern)))
    if level:query=query.where(MaterialCategoryRecord.level==level)
    total=db.scalar(select(func.count()).select_from(query.subquery())) or 0;items=list(db.scalars(query.order_by(MaterialCategoryRecord.code).offset((page-1)*page_size).limit(page_size)));return Page(items=items,page=page,page_size=page_size,total=total)


@router.get("/material-categories/tree",response_model=list[MaterialCategory])
def category_tree(db:Session=Depends(get_db)):
    return list(db.scalars(select(MaterialCategoryRecord).order_by(MaterialCategoryRecord.code)))


@router.post("/material-categories",response_model=MaterialCategory,status_code=201)
def create_category(payload:CategoryCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);parent=db.get(MaterialCategoryRecord,str(payload.parent_id)) if payload.parent_id else None
    if payload.parent_id and parent is None:raise HTTPException(status_code=404,detail="未找到上级分类")
    try:code,level,parent_name=organization_service.next_category_code(db,parent,payload.code_segment)
    except ValueError as error:raise HTTPException(status_code=409,detail=str(error)) from error
    if db.scalar(select(MaterialCategoryRecord.id).where(MaterialCategoryRecord.code==code)):raise HTTPException(status_code=409,detail="该分类编码已存在")
    path=f"{parent_name} / {payload.name}" if parent_name else payload.name;item=MaterialCategoryRecord(code=code,name=payload.name,level=level,parent_id=parent.id if parent else None,path_name=path,created_by=user.user_id);db.add(item);db.flush();_audit(db,user,"create","material_category",item.id,f"创建{level}级物料分类 {code} {path}");db.commit();db.refresh(item);return item


@router.patch("/material-categories/{item_id}",response_model=MaterialCategory)
def update_category(item_id:str,payload:CategoryUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=db.get(MaterialCategoryRecord,item_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到物料分类")
    values=payload.model_dump(exclude_none=True)
    for key,value in values.items():setattr(item,key,value)
    db.flush()
    if payload.name:
        parent=db.get(MaterialCategoryRecord,item.parent_id) if item.parent_id else None;item.path_name=f"{parent.path_name} / {item.name}" if parent else item.name
        descendants=list(db.scalars(select(MaterialCategoryRecord).where(MaterialCategoryRecord.code.like(f"{item.code}-%"))))
        for child in descendants:
            names=[db.scalar(select(MaterialCategoryRecord.name).where(MaterialCategoryRecord.code=="-".join(child.code.split("-")[:i]))) for i in range(1,child.level+1)];child.path_name=" / ".join(value for value in names if value)
        affected={node.id:node for node in [item,*descendants]}
        for link in db.scalars(select(MaterialCategoryAssignmentRecord).where(MaterialCategoryAssignmentRecord.category_id.in_(affected))):
            material=db.get(MaterialRecord,link.material_id)
            if material:material.category=affected[link.category_id].path_name
    db.flush();_audit(db,user,"update","material_category",item_id,f"更新物料分类 {item.code}");db.commit();db.refresh(item);return item


@router.delete("/material-categories/{item_id}",status_code=204)
def delete_category(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=db.get(MaterialCategoryRecord,item_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到物料分类")
    children=db.scalar(select(func.count()).select_from(MaterialCategoryRecord).where(MaterialCategoryRecord.parent_id==item_id)) or 0
    used=(db.scalar(select(func.count()).select_from(MaterialCategoryAssignmentRecord).where(MaterialCategoryAssignmentRecord.category_id==item_id)) or 0)+(db.scalar(select(func.count()).select_from(SupplierCategoryLinkRecord).where(SupplierCategoryLinkRecord.category_id==item_id)) or 0)
    authorized=db.scalar(select(BuyerCategoryAuthorizationRecord.id).where(BuyerCategoryAuthorizationRecord.category_id==item_id).limit(1))
    if children or used or authorized:raise HTTPException(status_code=409,detail="分类存在下级、采购授权或业务关联，不能删除")
    db.delete(item);_audit(db,user,"delete","material_category",item_id,f"删除物料分类 {item.code}");db.commit()


@router.put("/materials/{material_id}/category",response_model=MaterialAssignment)
def assign_material(material_id:str,payload:MaterialAssignment,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);material=db.get(MaterialRecord,material_id);category=db.get(MaterialCategoryRecord,str(payload.category_id))
    if material is None:raise HTTPException(status_code=404,detail="未找到物料")
    if category is None or category.level!=3:raise HTTPException(status_code=409,detail="物料必须指定到三级分类")
    link=db.scalar(select(MaterialCategoryAssignmentRecord).where(MaterialCategoryAssignmentRecord.material_id==material_id))
    if link is None:link=MaterialCategoryAssignmentRecord(material_id=material_id,category_id=category.id,created_by=user.user_id);db.add(link)
    else:link.category_id=category.id
    material.category=category.path_name;db.flush();_audit(db,user,"assign","material_category",material_id,f"物料 {material.code} 归类至 {category.code}");db.commit();return MaterialAssignment(material_id=material_id,category_id=category.id)


@router.get("/material-category-assignments")
def list_material_assignments(db:Session=Depends(get_db)):
    links=list(db.scalars(select(MaterialCategoryAssignmentRecord)));return [{"id":item.id,"material_id":item.material_id,"category_id":item.category_id} for item in links]


@router.get("/material-categories/{category_id}/next-material-code")
def next_material_code(category_id: str, db: Session=Depends(get_db)):
    category=db.get(MaterialCategoryRecord,category_id)
    if category is None or category.level!=3:raise HTTPException(status_code=409,detail="请选择三级分类")
    prefix=f"{category.code}-"
    codes=list(db.scalars(select(MaterialRecord.code).where(MaterialRecord.code.startswith(prefix))))
    numbers=[int(code[len(prefix):]) for code in codes if code[len(prefix):].isdigit()]
    return {"code":f"{prefix}{max(numbers,default=0)+1:04d}"}


@router.get("/staff-users",response_model=Page[StaffUser])
def list_staff(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),keyword:str="",status:str="",db:Session=Depends(get_db)):
    records,total=organization_service.list_records(db,StaffUserRecord,page,page_size,keyword,status);return Page(items=records,page=page,page_size=page_size,total=total)


@router.post("/staff-users",response_model=StaffUser,status_code=201)
def create_staff(payload:StaffCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user)
    if db.scalar(select(StaffUserRecord).where(StaffUserRecord.user_code==payload.user_code)):raise HTTPException(status_code=409,detail="人员编号已存在")
    item=StaffUserRecord(**payload.model_dump(),created_by=user.user_id);db.add(item);db.flush();_audit(db,user,"create","staff_user",item.id,f"创建人员 {item.user_code} {item.name}");db.commit();db.refresh(item);return item


@router.patch("/staff-users/{item_id}",response_model=StaffUser)
def update_staff(item_id:str,payload:StaffUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=db.get(StaffUserRecord,item_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到人员")
    for key,value in payload.model_dump(exclude_none=True).items():setattr(item,key,value)
    db.flush();_audit(db,user,"update","staff_user",item_id,f"更新人员 {item.user_code}");db.commit();db.refresh(item);return item


@router.delete("/staff-users/{item_id}",status_code=204)
def delete_staff(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=db.get(StaffUserRecord,item_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到人员")
    from app.domain.projects import ProjectRecord, project_data
    from app.domain.project_access import ProjectGrant
    if db.scalar(select(ProjectGrant.id).where(ProjectGrant.staff_id == item_id).limit(1)):
        raise HTTPException(409, '人员存在项目授权，请先撤销授权')
    for project in db.scalars(select(ProjectRecord)):
        data = project_data(project)
        if data.get('manager_id') == item_id or any(t.get('owner_id') == item_id for t in data['tasks']):
            raise HTTPException(409, '人员被项目或任务引用，请移交责任或保留人员档案')
    if db.scalar(select(func.count()).select_from(OrderBuyerAssignment).where(OrderBuyerAssignment.buyer_id==item_id)):raise HTTPException(status_code=409,detail="人员负责采购订单，请先移交订单再删除")
    if db.scalar(select(func.count()).select_from(BuyerCategoryAuthorizationRecord).where(BuyerCategoryAuthorizationRecord.buyer_id==item_id)):raise HTTPException(status_code=409,detail="人员存在采购分类授权，不能删除")
    db.delete(item);_audit(db,user,"delete","staff_user",item_id,"删除人员");db.commit()


@router.get("/buyer-authorizations",response_model=Page[BuyerAuthorization])
def list_authorizations(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    total=db.scalar(select(func.count()).select_from(BuyerCategoryAuthorizationRecord)) or 0;records=list(db.scalars(select(BuyerCategoryAuthorizationRecord).order_by(BuyerCategoryAuthorizationRecord.created_at.desc()).offset((page-1)*page_size).limit(page_size)));return Page(items=[organization_service.authorization(db,item) for item in records],page=page,page_size=page_size,total=total)


@router.post("/buyer-authorizations",response_model=BuyerAuthorization,status_code=201)
def create_authorization(payload:BuyerAuthorizationCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);buyer=db.get(StaffUserRecord,str(payload.buyer_id));category=db.get(MaterialCategoryRecord,str(payload.category_id))
    if buyer is None or buyer.role!="buyer":raise HTTPException(status_code=409,detail="授权对象必须是采购员")
    if category is None:raise HTTPException(status_code=404,detail="未找到物料分类")
    overlap=db.scalar(select(BuyerCategoryAuthorizationRecord).where(BuyerCategoryAuthorizationRecord.buyer_id==str(payload.buyer_id),BuyerCategoryAuthorizationRecord.category_id==str(payload.category_id),BuyerCategoryAuthorizationRecord.status=="active",BuyerCategoryAuthorizationRecord.valid_from<=payload.valid_to,BuyerCategoryAuthorizationRecord.valid_to>=payload.valid_from))
    if overlap:raise HTTPException(status_code=409,detail="采购员在该分类与有效期内已有授权")
    values=payload.model_dump();values["buyer_id"]=str(payload.buyer_id);values["category_id"]=str(payload.category_id)
    item=BuyerCategoryAuthorizationRecord(**values,created_by=user.user_id);db.add(item);db.flush();_audit(db,user,"authorize","buyer_category",item.id,f"授权 {buyer.name} 负责 {category.code}，有效期至 {payload.valid_to}");db.commit();db.refresh(item);return organization_service.authorization(db,item)


@router.patch("/buyer-authorizations/{item_id}",response_model=BuyerAuthorization)
def update_authorization(item_id:str,payload:BuyerAuthorizationUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=db.get(BuyerCategoryAuthorizationRecord,item_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到采购授权")
    values=payload.model_dump(exclude_none=True)
    for key,value in values.items():setattr(item,key,value)
    if item.valid_to<item.valid_from:raise HTTPException(status_code=422,detail="授权结束日期不能早于开始日期")
    db.flush();_audit(db,user,"update","buyer_category",item_id,"更新采购员分类授权");db.commit();db.refresh(item);return organization_service.authorization(db,item)


@router.delete("/buyer-authorizations/{item_id}",status_code=204)
def delete_authorization(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=db.get(BuyerCategoryAuthorizationRecord,item_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到采购授权")
    db.delete(item);_audit(db,user,"delete","buyer_category",item_id,"删除采购员分类授权");db.commit()


@router.get("/supplier-category-links",response_model=Page[SupplierCategoryLink])
def list_supplier_links(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    total=db.scalar(select(func.count()).select_from(SupplierCategoryLinkRecord)) or 0;records=list(db.scalars(select(SupplierCategoryLinkRecord).order_by(SupplierCategoryLinkRecord.created_at.desc()).offset((page-1)*page_size).limit(page_size)));return Page(items=[organization_service.supplier_link(db,item) for item in records],page=page,page_size=page_size,total=total)


@router.post("/supplier-category-links",response_model=SupplierCategoryLink,status_code=201)
def create_supplier_link(payload:SupplierCategoryLinkCreate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);supplier=db.get(SupplierRecord,str(payload.supplier_id));category=db.get(MaterialCategoryRecord,str(payload.category_id))
    if supplier is None or category is None:raise HTTPException(status_code=404,detail="未找到供应商或物料分类")
    exists=db.scalar(select(SupplierCategoryLinkRecord).where(SupplierCategoryLinkRecord.supplier_id==str(payload.supplier_id),SupplierCategoryLinkRecord.category_id==str(payload.category_id)))
    if exists:raise HTTPException(status_code=409,detail="供应商与物料分类已关联")
    item=SupplierCategoryLinkRecord(**payload.model_dump(mode="json"),created_by=user.user_id);db.add(item);db.flush();_audit(db,user,"link","supplier_category",item.id,f"关联 {supplier.code} 与 {category.code}");db.commit();db.refresh(item);return organization_service.supplier_link(db,item)


@router.patch("/supplier-category-links/{item_id}",response_model=SupplierCategoryLink)
def update_supplier_link(item_id:str,payload:SupplierCategoryLinkUpdate,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=db.get(SupplierCategoryLinkRecord,item_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到供应商分类关联")
    item.qualification_status=payload.qualification_status;db.flush();_audit(db,user,"update","supplier_category",item_id,"更新供应商分类资质状态");db.commit();db.refresh(item);return organization_service.supplier_link(db,item)


@router.delete("/supplier-category-links/{item_id}",status_code=204)
def delete_supplier_link(item_id:str,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    _manager(user);item=db.get(SupplierCategoryLinkRecord,item_id)
    if item is None:raise HTTPException(status_code=404,detail="未找到供应商分类关联")
    db.delete(item);_audit(db,user,"unlink","supplier_category",item_id,"解除供应商物料分类关联");db.commit()
