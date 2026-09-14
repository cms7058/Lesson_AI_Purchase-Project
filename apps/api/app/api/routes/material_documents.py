import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.material_documents import (
    MaterialDocumentDecision,
    MaterialDocumentEventRecord,
    MaterialDocumentUpdate,
    MaterialTechnicalDocumentRecord,
)
from app.domain.persistence import MaterialRecord
from app.services.audit_service import write_audit_log

router = APIRouter(tags=["material-technical-documents"])
FILES = Path("private_material_documents")
EDITORS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}
MANAGERS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}
TYPES = {"drawing", "specification", "inspection_standard", "certificate", "process_instruction", "other"}
SUFFIXES = {".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".dwg", ".dxf"}


def require_editor(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in EDITORS:
        raise HTTPException(403, "当前角色无权维护物料技术资料")
    return user


def require_manager(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in MANAGERS:
        raise HTTPException(403, "只有系统管理员或采购经理可以审批技术资料")
    return user


def material_or_404(db: Session, material_id: str) -> MaterialRecord:
    item = db.get(MaterialRecord, material_id)
    if not item:
        raise HTTPException(404, "未找到物料")
    return item


def document_or_404(db: Session, document_id: str) -> MaterialTechnicalDocumentRecord:
    item = db.get(MaterialTechnicalDocumentRecord, document_id)
    if not item:
        raise HTTPException(404, "未找到物料技术资料")
    return item


def view(item: MaterialTechnicalDocumentRecord) -> dict:
    return {key: getattr(item, key) for key in (
        "id", "material_id", "document_no", "title", "document_type", "version", "status",
        "effective_date", "description", "file_name", "file_size", "checksum", "created_by",
        "reviewed_by", "review_note", "reviewed_at", "created_at", "updated_at",
    )}


def event(db: Session, item: MaterialTechnicalDocumentRecord, action: str, user: CurrentUser, note: str = "") -> None:
    db.add(MaterialDocumentEventRecord(document_id=item.id, action=action, status=item.status, note=note, actor_id=user.user_id))
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action=action, resource_type="material_technical_document", resource_id=item.id, detail=f"{item.document_no} V{item.version} {note}".strip())


@router.get("/materials/{material_id}/technical-documents")
def list_documents(
    material_id: str,
    keyword: str = Query("", max_length=100),
    document_type: str = Query("", pattern="^(|drawing|specification|inspection_standard|certificate|process_instruction|other)$"),
    document_status: str = Query("", alias="status", pattern="^(|draft|pending_approval|active|obsolete)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    material = material_or_404(db, material_id)
    filters = [MaterialTechnicalDocumentRecord.material_id == material_id]
    if keyword:
        term = f"%{keyword.strip()}%"
        filters.append(or_(MaterialTechnicalDocumentRecord.document_no.ilike(term), MaterialTechnicalDocumentRecord.title.ilike(term), MaterialTechnicalDocumentRecord.version.ilike(term)))
    if document_type:
        filters.append(MaterialTechnicalDocumentRecord.document_type == document_type)
    if document_status:
        filters.append(MaterialTechnicalDocumentRecord.status == document_status)
    total = db.scalar(select(func.count()).select_from(MaterialTechnicalDocumentRecord).where(*filters)) or 0
    rows = db.scalars(select(MaterialTechnicalDocumentRecord).where(*filters).order_by(MaterialTechnicalDocumentRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    all_statuses = list(db.scalars(select(MaterialTechnicalDocumentRecord.status).where(MaterialTechnicalDocumentRecord.material_id == material_id)))
    return {"material": {"id": material.id, "code": material.code, "name": material.name, "specification": material.specification}, "items": [view(item) for item in rows], "total": total, "page": page, "page_size": page_size, "counts": {key: all_statuses.count(key) for key in ("draft", "pending_approval", "active", "obsolete")}}


@router.post("/materials/{material_id}/technical-documents", status_code=201)
async def create_document(
    material_id: str,
    document_no: str = Form(..., min_length=2, max_length=80),
    title: str = Form(..., min_length=2, max_length=200),
    document_type: str = Form(...),
    version: str = Form(..., min_length=1, max_length=30),
    effective_date: str = Form(""),
    description: str = Form("", max_length=2000),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_editor),
):
    material = material_or_404(db, material_id)
    if document_type not in TYPES:
        raise HTTPException(422, "技术资料类型无效")
    name = Path((file.filename or "document").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in SUFFIXES:
        raise HTTPException(422, "支持PDF、Word、Excel、图片、DWG和DXF文件")
    raw = await file.read(20 * 1024 * 1024 + 1)
    if not raw or len(raw) > 20 * 1024 * 1024:
        raise HTTPException(422, "技术资料须为1字节至20MB")
    date_value = None
    if effective_date:
        try:
            date_value = date.fromisoformat(effective_date)
        except ValueError as exc:
            raise HTTPException(422, "生效日期格式应为YYYY-MM-DD") from exc
    FILES.mkdir(exist_ok=True)
    storage = uuid4().hex + suffix
    (FILES / storage).write_bytes(raw)
    item = MaterialTechnicalDocumentRecord(material_id=material_id, document_no=document_no.strip(), title=title.strip(), document_type=document_type, version=version.strip(), effective_date=date_value, description=description.strip(), file_name=name[:240], storage_name=storage, file_size=len(raw), checksum=hashlib.sha256(raw).hexdigest(), created_by=user.user_id)
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback(); (FILES / storage).unlink(missing_ok=True)
        raise HTTPException(409, "该物料下的资料编号与版本已存在") from exc
    event(db, item, "create", user, f"为物料 {material.code} 上传资料")
    db.commit(); db.refresh(item)
    return view(item)


@router.patch("/material-technical-documents/{document_id}")
def update_document(document_id: str, payload: MaterialDocumentUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_editor)):
    item = document_or_404(db, document_id)
    if item.status != "draft":
        raise HTTPException(409, "只有草稿技术资料可以修改")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    event(db, item, "update", user, "更新资料元数据")
    db.commit(); db.refresh(item)
    return view(item)


@router.post("/material-technical-documents/{document_id}/submit")
def submit_document(document_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(require_editor)):
    item = document_or_404(db, document_id)
    if item.status != "draft":
        raise HTTPException(409, "只有草稿技术资料可以提交审批")
    item.status = "pending_approval"; event(db, item, "submit", user, "提交审批")
    db.commit(); db.refresh(item)
    return view(item)


@router.post("/material-technical-documents/{document_id}/decision")
def decide_document(document_id: str, payload: MaterialDocumentDecision, db: Session = Depends(get_db), user: CurrentUser = Depends(require_manager)):
    item = document_or_404(db, document_id)
    if item.status != "pending_approval":
        raise HTTPException(409, "只有待审批技术资料可以审批")
    if not payload.approved and not payload.note.strip():
        raise HTTPException(422, "驳回必须填写原因")
    if payload.approved:
        previous = db.scalars(select(MaterialTechnicalDocumentRecord).where(MaterialTechnicalDocumentRecord.material_id == item.material_id, MaterialTechnicalDocumentRecord.document_no == item.document_no, MaterialTechnicalDocumentRecord.status == "active", MaterialTechnicalDocumentRecord.id != item.id))
        for old in previous:
            old.status = "obsolete"; event(db, old, "obsolete", user, f"由V{item.version}替代")
        item.status = "active"
    else:
        item.status = "draft"
    item.reviewed_by = user.user_id; item.reviewed_at = datetime.now(UTC); item.review_note = payload.note.strip()
    event(db, item, "approve" if payload.approved else "reject", user, payload.note.strip() or "审批通过")
    db.commit(); db.refresh(item)
    return view(item)


@router.get("/material-technical-documents/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db)):
    item = document_or_404(db, document_id)
    path = FILES / item.storage_name
    if not path.is_file():
        raise HTTPException(404, "技术资料文件不存在")
    return FileResponse(path, filename=item.file_name, media_type="application/octet-stream", headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'"})


@router.get("/material-technical-documents/{document_id}/history")
def document_history(document_id: str, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    document_or_404(db, document_id)
    criteria = MaterialDocumentEventRecord.document_id == document_id
    total = db.scalar(select(func.count()).select_from(MaterialDocumentEventRecord).where(criteria)) or 0
    rows = db.scalars(select(MaterialDocumentEventRecord).where(criteria).order_by(MaterialDocumentEventRecord.created_at.desc(), MaterialDocumentEventRecord.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [{"id": row.id, "action": row.action, "status": row.status, "note": row.note, "actor_id": row.actor_id, "created_at": row.created_at} for row in rows], "total": total, "page": page, "page_size": page_size}


@router.delete("/material-technical-documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(require_editor)):
    item = document_or_404(db, document_id)
    if item.status != "draft":
        raise HTTPException(409, "只有草稿技术资料可以删除")
    path = FILES / item.storage_name
    for row in db.scalars(select(MaterialDocumentEventRecord).where(MaterialDocumentEventRecord.document_id == item.id)):
        db.delete(row)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="delete", resource_type="material_technical_document", resource_id=item.id, detail=f"删除 {item.document_no} V{item.version}")
    db.delete(item); db.commit()
    if path.is_file():
        path.unlink()
