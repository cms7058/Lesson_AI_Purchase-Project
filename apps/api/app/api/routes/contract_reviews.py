import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.ai_settings import effective_ai_config
from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.contract_reviews import ContractDocumentRecord, ContractReviewRecord
from app.domain.persistence import ContractRecord
from app.services.audit_service import write_audit_log
from app.services.contract_ai_review import (
    ContractParseError,
    extract_contract_text,
    review_contract,
)

router = APIRouter(tags=["contract-ai-review"])
FILES = Path("private_contract_documents")
EDITORS = {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}


class ReviewInput(BaseModel):
    document_id: str | None = None


def require_editor(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in EDITORS:
        raise HTTPException(403, "当前角色无权上传或审查合同")
    return user


def contract_or_404(db: Session, contract_id: str) -> ContractRecord:
    item = db.get(ContractRecord, contract_id)
    if not item:
        raise HTTPException(404, "未找到合同")
    return item


def document_view(item: ContractDocumentRecord, reviewed_ids: set[str] | None = None) -> dict:
    return {
        "id": item.id,
        "contract_id": item.contract_id,
        "version": item.version,
        "file_name": item.file_name,
        "file_type": item.file_type,
        "extraction_mode": item.extraction_mode,
        "text_length": len(item.extracted_text),
        "reviewed": item.id in (reviewed_ids or set()),
        "created_by": item.created_by,
        "created_at": item.created_at,
    }


def review_view(item: ContractReviewRecord) -> dict:
    result = json.loads(item.result_json)
    return {
        "id": item.id,
        "contract_id": item.contract_id,
        "document_id": item.document_id,
        "document_version": item.document_version,
        "engine": item.engine,
        "risk_level": item.risk_level,
        "risk_score": item.risk_score,
        "result": result,
        "created_by": item.created_by,
        "created_at": item.created_at,
    }


@router.get("/contracts/{contract_id}/review-workspace")
def review_workspace(contract_id: str, db: Session = Depends(get_db)):
    contract = contract_or_404(db, contract_id)
    documents = list(db.scalars(select(ContractDocumentRecord).where(ContractDocumentRecord.contract_id == contract_id).order_by(ContractDocumentRecord.version.desc())))
    reviewed_ids = set(db.scalars(select(ContractReviewRecord.document_id).where(ContractReviewRecord.contract_id == contract_id)))
    latest_review = db.scalars(select(ContractReviewRecord).where(ContractReviewRecord.contract_id == contract_id).order_by(ContractReviewRecord.created_at.desc(), ContractReviewRecord.id.desc()).limit(1)).first()
    return {
        "contract": {"id": contract.id, "contract_no": contract.contract_no, "title": contract.title, "supplier_name": contract.supplier_name, "amount": float(contract.amount), "currency": contract.currency, "status": contract.status},
        "documents": [document_view(item, reviewed_ids) for item in documents],
        "latest_review": review_view(latest_review) if latest_review else None,
        "current_document_reviewed": bool(documents and documents[0].id in reviewed_ids),
    }


@router.post("/contracts/{contract_id}/documents", status_code=201)
async def upload_contract_document(contract_id: str, file: UploadFile = File(...), db: Session = Depends(get_db), user: CurrentUser = Depends(require_editor)):
    contract = contract_or_404(db, contract_id)
    if contract.status != "draft":
        raise HTTPException(409, "只有草稿合同可以上传新版本")
    name = Path((file.filename or "contract").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in {".txt", ".docx", ".pdf"}:
        raise HTTPException(422, "合同文件仅支持TXT、DOCX和可检索文本PDF")
    raw = await file.read(10 * 1024 * 1024 + 1)
    if not raw or len(raw) > 10 * 1024 * 1024:
        raise HTTPException(422, "合同文件须为1字节至10MB")
    try:
        extracted, mode = extract_contract_text(raw, name)
    except ContractParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    version = (db.scalar(select(func.max(ContractDocumentRecord.version)).where(ContractDocumentRecord.contract_id == contract_id)) or 0) + 1
    FILES.mkdir(exist_ok=True)
    storage = uuid4().hex + suffix
    (FILES / storage).write_bytes(raw)
    item = ContractDocumentRecord(contract_id=contract_id, version=version, file_name=name[:240], storage_name=storage, file_type=suffix[1:], extracted_text=extracted, extraction_mode=mode, created_by=user.user_id)
    db.add(item); db.flush()
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="upload", resource_type="contract_document", resource_id=item.id, detail=f"上传合同 {contract.contract_no} V{version}：{name}")
    db.commit(); db.refresh(item)
    return document_view(item)


@router.get("/contract-documents/{document_id}/download")
def download_contract_document(document_id: str, db: Session = Depends(get_db)):
    item = db.get(ContractDocumentRecord, document_id)
    if not item:
        raise HTTPException(404, "未找到合同文件")
    path = FILES / item.storage_name
    if not path.is_file():
        raise HTTPException(404, "合同文件不存在")
    return FileResponse(path, filename=item.file_name, media_type="application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/contract-documents/{document_id}", status_code=204)
def delete_contract_document(document_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(require_editor)):
    item = db.get(ContractDocumentRecord, document_id)
    if not item:
        raise HTTPException(404, "未找到合同文件")
    contract = contract_or_404(db, item.contract_id)
    if contract.status != "draft":
        raise HTTPException(409, "只有草稿合同可以删除文件")
    reviewed = db.scalar(select(func.count()).select_from(ContractReviewRecord).where(ContractReviewRecord.document_id == item.id)) or 0
    if reviewed:
        raise HTTPException(409, "已形成AI审查记录的合同版本不可删除")
    path = FILES / item.storage_name
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="delete", resource_type="contract_document", resource_id=item.id, detail=f"删除合同 {contract.contract_no} V{item.version} 文件")
    db.delete(item); db.commit()
    if path.is_file():
        path.unlink()


@router.post("/contracts/{contract_id}/ai-review", status_code=201)
def run_contract_review(contract_id: str, payload: ReviewInput, db: Session = Depends(get_db), user: CurrentUser = Depends(require_editor)):
    contract = contract_or_404(db, contract_id)
    query = select(ContractDocumentRecord).where(ContractDocumentRecord.contract_id == contract_id)
    if payload.document_id:
        query = query.where(ContractDocumentRecord.id == payload.document_id)
    document = db.scalars(query.order_by(ContractDocumentRecord.version.desc()).limit(1)).first()
    if not document:
        raise HTTPException(409, "请先上传合同文件")
    result, engine = review_contract(document.extracted_text, contract, effective_ai_config(db))
    item = ContractReviewRecord(contract_id=contract_id, document_id=document.id, document_version=document.version, engine=engine, risk_level=result["risk_level"], risk_score=result["risk_score"], result_json=json.dumps(result, ensure_ascii=False), created_by=user.user_id)
    db.add(item); db.flush()
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="ai_review", resource_type="contract", resource_id=contract_id, detail=f"完成合同V{document.version} AI审查：{result['risk_level']} / {result['risk_score']}分")
    db.commit(); db.refresh(item)
    return review_view(item)


@router.get("/contracts/{contract_id}/ai-reviews")
def list_contract_reviews(contract_id: str, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    contract_or_404(db, contract_id)
    criteria = ContractReviewRecord.contract_id == contract_id
    total = db.scalar(select(func.count()).select_from(ContractReviewRecord).where(criteria)) or 0
    rows = db.scalars(select(ContractReviewRecord).where(criteria).order_by(ContractReviewRecord.created_at.desc(), ContractReviewRecord.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [review_view(item) for item in rows], "total": total, "page": page, "page_size": page_size}
