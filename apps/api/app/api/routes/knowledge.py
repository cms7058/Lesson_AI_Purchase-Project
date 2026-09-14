import io
from datetime import datetime
from typing import Annotated, Literal

from docx import Document
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.knowledge import KnowledgeDocumentRecord
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
WRITE_ROLES = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}
ALLOWED = {".txt", ".md", ".pdf", ".docx"}
MAX_BYTES = 10 * 1024 * 1024


class KnowledgeInput(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    domain: Literal["procurement", "project", "shared"] = "procurement"
    document_type: Literal["policy", "procedure", "guide", "case", "faq", "training"] = "guide"
    source_name: str = Field(default="manual", max_length=240)
    tags: str = Field(default="", max_length=500)
    content: str = Field(min_length=10, max_length=500_000)
    status: Literal["draft", "active", "archived"] = "active"
    version: int | None = None


def _write(user: CurrentUser) -> None:
    if user.role not in WRITE_ROLES:
        raise HTTPException(403, "需要采购经理或管理员权限")


def _out(row: KnowledgeDocumentRecord) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "domain": row.domain,
        "document_type": row.document_type,
        "source_name": row.source_name,
        "tags": row.tags,
        "content": row.content,
        "status": row.status,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


@router.get("")
def list_knowledge(
    keyword: str = "",
    domain: str = "",
    status: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    conditions = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                KnowledgeDocumentRecord.title.ilike(pattern),
                KnowledgeDocumentRecord.tags.ilike(pattern),
                KnowledgeDocumentRecord.content.ilike(pattern),
                KnowledgeDocumentRecord.source_name.ilike(pattern),
            )
        )
    if domain:
        conditions.append(KnowledgeDocumentRecord.domain == domain)
    if status:
        conditions.append(KnowledgeDocumentRecord.status == status)
    statement = select(KnowledgeDocumentRecord).where(*conditions)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(
        statement.order_by(KnowledgeDocumentRecord.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {"items": [_out(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.post("")
def create_knowledge(payload: KnowledgeInput, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _write(user)
    row = KnowledgeDocumentRecord(**payload.model_dump(exclude={"version"}), created_by=user.user_id)
    db.add(row)
    db.flush()
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="create", resource_type="knowledge_document", resource_id=row.id, detail=row.title)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.put("/{item_id}")
def update_knowledge(item_id: str, payload: KnowledgeInput, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _write(user)
    row = db.get(KnowledgeDocumentRecord, item_id)
    if row is None:
        raise HTTPException(404, "未找到知识文档")
    if payload.version is not None and payload.version != row.version:
        raise HTTPException(409, "文档已被其他用户更新，请刷新后重试")
    for key, value in payload.model_dump(exclude={"version"}).items():
        setattr(row, key, value)
    row.version += 1
    row.updated_at = datetime.now().astimezone().replace(tzinfo=None)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="update", resource_type="knowledge_document", resource_id=row.id, detail=row.title)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/{item_id}")
def delete_knowledge(item_id: str, version: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _write(user)
    row = db.get(KnowledgeDocumentRecord, item_id)
    if row is None:
        raise HTTPException(404, "未找到知识文档")
    if row.version != version:
        raise HTTPException(409, "文档已被其他用户更新，请刷新后重试")
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="delete", resource_type="knowledge_document", resource_id=row.id, detail=row.title)
    db.delete(row)
    db.commit()
    return {"ok": True}


def _extract(name: str, data: bytes) -> str:
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix not in ALLOWED:
        raise HTTPException(415, "仅支持TXT、Markdown、PDF和DOCX")
    try:
        if suffix in {".txt", ".md"}:
            return data.decode("utf-8-sig")
        if suffix == ".pdf":
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
        return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(data)).paragraphs)
    except Exception as exc:
        raise HTTPException(422, "文件无法解析，请确认未加密且格式正确") from exc


@router.post("/upload")
async def upload_knowledge(
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    domain: Annotated[str, Form()] = "procurement",
    document_type: Annotated[str, Form()] = "guide",
    tags: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _write(user)
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "文件不得超过10MB")
    content = _extract(file.filename or "", data).strip()
    if len(content) < 10:
        raise HTTPException(422, "未提取到足够文本；扫描件请先OCR后导入")
    payload = KnowledgeInput(title=title, domain=domain, document_type=document_type, source_name=file.filename or "upload", tags=tags, content=content, status="active")
    return create_knowledge(payload, db, user)
