import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.ai_settings import effective_ai_config
from app.core.database import get_db
from app.core.security import CurrentUser, UserRole, get_current_user
from app.domain.persistence import QuotationRecord, RFQInvitationRecord, RFQRecord, SupplierRecord
from app.domain.quotations import QuotationCreate, QuotationLineInput
from app.domain.supplier_portal import (
    MailSettings,
    QuotationAttachment,
    QuotationReview,
    RFQAttachment,
    RFQMail,
    SupplierAccount,
    SupplierSession,
    SupplierSubmission,
)
from app.services.audit_service import write_audit_log
from app.services.quotation_document_parser import parse_quotation
from app.services.quotation_service import _to_domain as quote_domain
from app.services.quotation_service import quotation_service
from app.services.quotation_vision import VisionExtractionError, extract_visual_quotation
from app.services.rfq_mail import cipher, dispatch_rfq, queue_invitations
from app.services.rfq_service import _to_domain, rfq_service

router = APIRouter(tags=["supplier-portal"])
FILES = Path("private_rfq_attachments")


def manager(user: CurrentUser = Depends(get_current_user)):
    if user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER}:
        raise HTTPException(403, "需要采购经理权限")
    return user


def administrator(user: CurrentUser = Depends(get_current_user)):
    if user.role != UserRole.ADMIN:
        raise HTTPException(403, "仅系统管理员可以查看和维护供应商账号")
    return user


@router.get("/identity")
def identity(user: CurrentUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "role": user.role}


def editor(user: CurrentUser = Depends(get_current_user)):
    if user.role not in {UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER, UserRole.BUYER}:
        raise HTTPException(403, "无权管理询价")
    return user


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()


def supplier_user(authorization: str = Header(""), db: Session = Depends(get_db)):
    token = authorization.removeprefix("Bearer ")
    session = db.get(SupplierSession, hashlib.sha256(token.encode()).hexdigest())
    account = db.get(SupplierAccount, session.account_id) if session and session.expires_at > datetime.now(UTC).replace(tzinfo=None) else None
    supplier = db.get(SupplierRecord, account.supplier_id) if account else None
    if not account or not account.active or not supplier or supplier.status != "qualified":
        raise HTTPException(401, "请登录有效供应商账号")
    return account


class AccountInput(BaseModel):
    supplier_id: str
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str | None = Field(default=None, min_length=12, max_length=128)
    active: bool = True


@router.get("/supplier-accounts", dependencies=[Depends(administrator)])
def accounts(db: Session = Depends(get_db), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    items = db.scalars(select(SupplierAccount).offset((page-1)*page_size).limit(page_size))
    return {"items": [{"id": a.id, "supplier_id": a.supplier_id, "username": a.username, "active": a.active} for a in items], "total": db.scalar(select(func.count()).select_from(SupplierAccount)), "page": page, "page_size": page_size}


@router.get("/supplier-accounts/portal", dependencies=[Depends(administrator)])
def account_portal(db: Session = Depends(get_db)):
    settings = db.get(MailSettings, 1)
    return {"url": settings.portal_url if settings else "/supplier"}


@router.put("/supplier-accounts", dependencies=[Depends(administrator)])
def save_account(payload: AccountInput, db: Session = Depends(get_db), user=Depends(administrator)):
    supplier = db.get(SupplierRecord, payload.supplier_id)
    if not supplier:
        raise HTTPException(404, "未找到供应商")
    account = db.scalar(select(SupplierAccount).where(SupplierAccount.supplier_id == supplier.id))
    if not account and not payload.password:
        raise HTTPException(422, "新账号必须设置至少12位密码")
    duplicate = db.scalar(select(SupplierAccount).where(SupplierAccount.username == payload.username))
    if duplicate and (not account or duplicate.id != account.id):
        raise HTTPException(409, "登录名已存在")
    if not account:
        account = SupplierAccount(supplier_id=supplier.id, username=payload.username, password_hash=password_hash(payload.password))
        db.add(account)
        db.flush()
    account.username = payload.username
    account.active = payload.active
    if payload.password:
        account.password_hash = password_hash(payload.password)
        account.failures = 0
        account.locked_until = None
    db.execute(delete(SupplierSession).where(SupplierSession.account_id == account.id))
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="update", resource_type="supplier_account", resource_id=account.id, detail="更新供应商账号及会话授权（不记录密码）")
    db.commit()
    return {"id": account.id, "username": account.username}


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=128)


@router.post("/supplier/login")
def login(payload: Login, db: Session = Depends(get_db)):
    account = db.scalar(select(SupplierAccount).where(SupplierAccount.username == payload.username))
    now = datetime.now(UTC).replace(tzinfo=None)
    valid = account and account.active and (not account.locked_until or account.locked_until <= now)
    if not valid or not hmac.compare_digest(account.password_hash, password_hash(payload.password, account.password_hash.split(":")[0])):
        if account:
            account.failures += 1
            if account.failures >= 5:
                account.locked_until = now + timedelta(minutes=15)
            db.commit()
        raise HTTPException(401, "账号或密码错误，连续失败后请15分钟后再试")
    account.failures = 0
    token = secrets.token_urlsafe(40)
    db.add(SupplierSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), account_id=account.id, expires_at=now+timedelta(hours=8)))
    db.commit()
    return {"token": token, "username": account.username}


@router.post("/supplier/logout")
def logout(authorization: str = Header(""), db: Session = Depends(get_db)):
    db.execute(delete(SupplierSession).where(SupplierSession.token_hash == hashlib.sha256(authorization.removeprefix("Bearer ").encode()).hexdigest()))
    db.commit()
    return {"ok": True}


def invitation_for(db, rfq_id, account):
    supplier = db.get(SupplierRecord, account.supplier_id)
    inv = db.scalar(select(RFQInvitationRecord).where(RFQInvitationRecord.rfq_id == rfq_id, RFQInvitationRecord.supplier_id.in_([supplier.id, supplier.code])))
    rfq = rfq_service.get(db, rfq_id)
    if not inv or not rfq or rfq.status in {"draft", "cancelled"}:
        raise HTTPException(404, "未找到询价邀请")
    return rfq, inv


@router.get("/supplier/rfqs")
def supplier_rfqs(account=Depends(supplier_user), db: Session = Depends(get_db), tab: str = "pending", page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    supplier = db.get(SupplierRecord, account.supplier_id)
    filters = [RFQInvitationRecord.supplier_id.in_([supplier.id, supplier.code]), RFQRecord.status.notin_(["draft", "cancelled"])]
    if tab == "history":
        filters.extend([RFQInvitationRecord.quotation_id.is_not(None), or_(QuotationReview.status.is_(None), QuotationReview.status != "rejected")])
    else:
        filters.append(or_(RFQInvitationRecord.quotation_id.is_(None), QuotationReview.status == "rejected"))
    query = select(RFQRecord).join(RFQInvitationRecord, RFQInvitationRecord.rfq_id == RFQRecord.id).outerjoin(QuotationReview, QuotationReview.quotation_id == RFQInvitationRecord.quotation_id).where(*filters)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = []
    for r in db.scalars(query.order_by(RFQRecord.created_at.desc()).offset((page-1)*page_size).limit(page_size)):
        _, inv = invitation_for(db, r.id, account)
        review = db.get(QuotationReview, inv.quotation_id) if inv.quotation_id else None
        review_status = review.status if review else "pending"
        items.append({"id": r.id, "rfq_no": r.rfq_no, "title": r.title, "deadline": r.deadline, "currency": r.currency, "status": r.status, "responded": bool(inv.quotation_id) and review_status != "rejected", "review_status": review_status})
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def attachment_list(db, rfq_id):
    return [{"id": a.id, "name": a.name, "size": a.size} for a in db.scalars(select(RFQAttachment).where(RFQAttachment.rfq_id == rfq_id))]


def quote_attachments(db, *filters):
    return [{"id": a.id, "name": a.name, "size": a.size, "submitted": bool(a.quotation_id)} for a in db.scalars(select(QuotationAttachment).where(*filters))]


@router.get("/supplier/rfqs/{rfq_id}")
def supplier_detail(rfq_id: str, account=Depends(supplier_user), db: Session = Depends(get_db)):
    rfq, inv = invitation_for(db, rfq_id, account)
    data = _to_domain(rfq).model_dump(exclude={"invitations", "awarded_quotation_id", "created_by", "requisition_id"})
    data["attachments"] = attachment_list(db, rfq_id)
    data["quotation_attachments"] = quote_attachments(db, QuotationAttachment.rfq_id == rfq_id, QuotationAttachment.supplier_id == account.supplier_id)
    data["quotation"] = quote_domain(db.get(QuotationRecord, inv.quotation_id), db) if inv.quotation_id else None
    review = db.get(QuotationReview, inv.quotation_id) if inv.quotation_id else None
    data["review"] = {"status": review.status, "note": review.note} if review else {"status": "pending", "note": ""}
    return data


class Price(BaseModel):
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.13"), ge=0, le=1)
    logistics_cost: Decimal = Field(default=Decimal(0), ge=0)


class Bid(BaseModel):
    lines: list[Price] = Field(min_length=1)
    delivery_days: int = Field(ge=0, le=999)
    validity_days: int = Field(default=30, ge=1, le=365)
    source_type: str = Field(default="manual", pattern="^(manual|ocr)$")


@router.post("/supplier/rfqs/{rfq_id}/quote", status_code=201)
def submit_quote(rfq_id: str, payload: Bid, account=Depends(supplier_user), db: Session = Depends(get_db)):
    rfq, inv = invitation_for(db, rfq_id, account)
    previous_review = db.get(QuotationReview, inv.quotation_id) if inv.quotation_id else None
    revising = bool(previous_review and previous_review.status == "rejected")
    if rfq.status != "published" or (rfq.deadline and rfq.deadline < datetime.now(ZoneInfo("Asia/Shanghai")).date()) or (inv.quotation_id and not revising):
        raise HTTPException(409, "询价已截止、已定标或您已提交报价")
    if len(payload.lines) != len(rfq.lines):
        raise HTTPException(422, "请完整填写全部询价物料报价")
    supplier = db.get(SupplierRecord, account.supplier_id)
    lines = [QuotationLineInput(material_code=line.material_code, material_name=line.material_name, quantity=line.quantity, unit=line.unit, **price.model_dump()) for line, price in zip(rfq.lines, payload.lines, strict=True)]
    quote = quotation_service.create_quotation(db, QuotationCreate(supplier_id=inv.supplier_id, supplier_name=supplier.name, currency=rfq.currency, delivery_days=payload.delivery_days, validity_days=payload.validity_days, source_type=payload.source_type, lines=lines), f"supplier:{account.id}")
    inv.quotation_id = str(quote.id)
    inv.status = "responded"
    for attachment in db.scalars(select(QuotationAttachment).where(QuotationAttachment.rfq_id == rfq.id, QuotationAttachment.supplier_id == supplier.id, QuotationAttachment.quotation_id.is_(None))):
        attachment.quotation_id = str(quote.id)
    submission = db.scalar(select(SupplierSubmission).where(SupplierSubmission.rfq_id == rfq.id, SupplierSubmission.supplier_id == supplier.id))
    if submission:
        submission.quotation_id = str(quote.id)
    else:
        db.add(SupplierSubmission(rfq_id=rfq.id, supplier_id=supplier.id, quotation_id=str(quote.id)))
    write_audit_log(db, actor_id=account.id, actor_role="supplier", action="quote", resource_type="rfq_project", resource_id=rfq.id, detail=f"供应商在线提交报价 {quote.quotation_no}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "您已提交报价，请刷新查看") from None
    return quote


@router.get("/rfqs/{rfq_id}/bids", dependencies=[Depends(editor)])
def bids(rfq_id: str, db: Session = Depends(get_db)):
    rfq = rfq_service.get(db, rfq_id)
    if not rfq:
        raise HTTPException(404, "未找到询价")
    quote_records = [db.get(QuotationRecord, inv.quotation_id) for inv in rfq.invitations if inv.quotation_id]
    prices: dict[str, list[Decimal]] = {}
    for candidate in quote_records:
        if candidate:
            for line in candidate.lines:
                if line.unit_price > 0:
                    prices.setdefault(line.material_code, []).append(line.unit_price)
    rows = []
    for inv in rfq.invitations:
        quote = db.get(QuotationRecord, inv.quotation_id) if inv.quotation_id else None
        mail = db.scalar(select(RFQMail).where(RFQMail.rfq_id == rfq_id, RFQMail.supplier_id == inv.supplier_id))
        review = db.get(QuotationReview, quote.id) if quote else None
        anomalies = []
        cost = None
        if quote:
            goods = sum(line.quantity * line.unit_price for line in quote.lines)
            tax = sum(line.quantity * line.unit_price * line.tax_rate for line in quote.lines)
            logistics = sum(line.logistics_cost for line in quote.lines)
            cost = {"goods_before_tax": goods, "tax": tax, "logistics": logistics, "landed_total": goods + tax + logistics}
            for line in quote.lines:
                peers = sorted(prices.get(line.material_code, []))
                median = (peers[(len(peers) - 1) // 2] + peers[len(peers) // 2]) / 2 if peers else Decimal(0)
                if line.unit_price <= 0:
                    anomalies.append({"level": "critical", "material_code": line.material_code, "message": "报价单价为0，必须退回核实"})
                elif len(peers) >= 2 and median and abs(line.unit_price - median) / median > Decimal("0.2"):
                    anomalies.append({"level": "warning", "material_code": line.material_code, "message": "单价偏离本次有效报价中位数超过20%"})
                if line.logistics_cost > line.quantity * line.unit_price * Decimal("0.2"):
                    anomalies.append({"level": "warning", "material_code": line.material_code, "message": "物流费超过未税货值20%"})
        reviewed_ids = list(db.scalars(select(QuotationReview.quotation_id).where(QuotationReview.rfq_id == rfq_id)))
        revision_ids = set(reviewed_ids)
        if quote:
            revision_ids.add(quote.id)
        revisions = []
        if revision_ids:
            candidates = list(db.scalars(select(QuotationRecord).where(QuotationRecord.id.in_(revision_ids), QuotationRecord.supplier_id == inv.supplier_id).order_by(QuotationRecord.created_at)))
            candidates.sort(key=lambda candidate: (bool(quote and candidate.id == quote.id), candidate.created_at, candidate.id))
            for version, candidate in enumerate(candidates, 1):
                candidate_review = db.get(QuotationReview, candidate.id)
                candidate_total = sum(line.quantity * line.unit_price * (1 + line.tax_rate) + line.logistics_cost for line in candidate.lines)
                revisions.append({"quotation_id": candidate.id, "quotation_no": candidate.quotation_no, "version": version, "current": bool(quote and candidate.id == quote.id), "source_type": candidate.source_type, "created_at": candidate.created_at, "total": candidate_total, "review": {"status": candidate_review.status, "note": candidate_review.note, "reviewed_at": candidate_review.reviewed_at} if candidate_review else {"status": "pending", "note": "", "reviewed_at": None}})
        rows.append({"supplier_name": inv.supplier_name, "supplier_id": inv.supplier_id, "status": "responded" if quote else "pending", "quotation": quote_domain(quote, db) if quote else None, "mail_status": mail.status if mail else "not_queued", "mail_error": mail.error if mail else "", "cost_summary": cost, "anomalies": anomalies, "review": {"status": review.status, "reviewer_id": review.reviewer_id, "note": review.note, "reviewed_at": review.reviewed_at} if review else {"status": "pending", "reviewer_id": "", "note": "", "reviewed_at": None}, "revision_history": revisions})
        rows[-1]["quotation_attachments"] = quote_attachments(db, QuotationAttachment.rfq_id == rfq_id, QuotationAttachment.quotation_id == quote.id) if quote else []
    return {"items": rows, "attachments": attachment_list(db, rfq_id)}


class ReviewInput(BaseModel):
    status: str = Field(pattern="^(verified|rejected)$")
    note: str = Field(default="", max_length=1000)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value):
        return value.strip()


@router.put("/rfqs/{rfq_id}/quotations/{quotation_id}/review", dependencies=[Depends(editor)])
def review_quotation(rfq_id: str, quotation_id: str, payload: ReviewInput, db: Session = Depends(get_db), user=Depends(editor)):
    invitation = db.scalar(select(RFQInvitationRecord).where(RFQInvitationRecord.rfq_id == rfq_id, RFQInvitationRecord.quotation_id == quotation_id))
    if not invitation or not db.get(QuotationRecord, quotation_id):
        raise HTTPException(404, "该报价不属于当前询价")
    quote = db.get(QuotationRecord, quotation_id)
    if payload.status == "rejected" and not payload.note:
        raise HTTPException(422, "退回报价必须填写原因")
    if payload.status == "verified" and any(line.unit_price <= 0 for line in quote.lines):
        raise HTTPException(409, "存在单价为0的明细，不能核验通过，请退回供应商核实")
    item = db.get(QuotationReview, quotation_id) or QuotationReview(quotation_id=quotation_id, rfq_id=rfq_id)
    item.status, item.note, item.reviewer_id, item.reviewed_at = payload.status, payload.note, user.user_id, datetime.now(UTC).replace(tzinfo=None)
    db.add(item)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="review", resource_type="quotation", resource_id=quotation_id, detail=f"报价复核：{payload.status}（备注不写入操作摘要）")
    db.commit()
    return {"status": item.status, "reviewer_id": item.reviewer_id, "note": item.note, "reviewed_at": item.reviewed_at}


@router.post("/rfqs/{rfq_id}/attachments", dependencies=[Depends(editor)], status_code=201)
async def upload_attachment(rfq_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    rfq = db.get(RFQRecord, rfq_id)
    if not rfq or rfq.status != "draft":
        raise HTTPException(409, "仅草稿询价可以上传附件")
    name = Path(file.filename or "attachment").name
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".csv", ".txt", ".zip"}:
        raise HTTPException(422, "不支持此附件类型")
    data = await file.read(10*1024*1024+1)
    if len(data) > 10*1024*1024 or not data:
        raise HTTPException(422, "附件须为1字节至10MB")
    FILES.mkdir(exist_ok=True)
    filename = uuid4().hex + suffix
    (FILES / filename).write_bytes(data)
    item = RFQAttachment(rfq_id=rfq_id, name=name[:200], storage_name=filename, size=len(data))
    db.add(item)
    db.commit()
    return {"id": item.id, "name": item.name}


@router.delete("/rfqs/{rfq_id}/attachments/{attachment_id}", dependencies=[Depends(editor)], status_code=204)
def remove_attachment(rfq_id: str, attachment_id: str, db: Session = Depends(get_db)):
    rfq = db.get(RFQRecord, rfq_id)
    item = db.get(RFQAttachment, attachment_id)
    if not rfq or rfq.status != "draft" or not item or item.rfq_id != rfq_id:
        raise HTTPException(409, "附件不存在或询价已发布")
    path = FILES / item.storage_name
    db.delete(item)
    db.commit()
    path.unlink(missing_ok=True)


def download(db, rfq_id, attachment_id):
    item = db.get(RFQAttachment, attachment_id)
    if not item or item.rfq_id != rfq_id or not (FILES / item.storage_name).is_file():
        raise HTTPException(404, "附件不存在")
    return FileResponse(FILES / item.storage_name, filename=item.name, media_type="application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})


@router.get("/rfqs/{rfq_id}/attachments/{attachment_id}", dependencies=[Depends(editor)])
def internal_download(rfq_id: str, attachment_id: str, db: Session = Depends(get_db)):
    return download(db, rfq_id, attachment_id)


@router.get("/supplier/rfqs/{rfq_id}/attachments/{attachment_id}")
def supplier_download(rfq_id: str, attachment_id: str, account=Depends(supplier_user), db: Session = Depends(get_db)):
    invitation_for(db, rfq_id, account)
    return download(db, rfq_id, attachment_id)


def require_open_quote_for(db, rfq, invitation):
    review = db.get(QuotationReview, invitation.quotation_id) if invitation.quotation_id else None
    if rfq.status != "published" or (invitation.quotation_id and (not review or review.status != "rejected")) or (rfq.deadline and rfq.deadline < datetime.now(ZoneInfo("Asia/Shanghai")).date()):
        raise HTTPException(409, "报价已提交或询价已截止，附件不可修改")


@router.post("/supplier/rfqs/{rfq_id}/quotation-attachments", status_code=201)
async def upload_quote_attachment(rfq_id: str, file: UploadFile = File(...), account=Depends(supplier_user), db: Session = Depends(get_db)):
    rfq, invitation = invitation_for(db, rfq_id, account)
    require_open_quote_for(db, rfq, invitation)
    count = db.scalar(select(func.count()).select_from(QuotationAttachment).where(QuotationAttachment.rfq_id == rfq_id, QuotationAttachment.supplier_id == account.supplier_id))
    if count >= 20:
        raise HTTPException(409, "每次报价最多上传20个附件")
    name = Path((file.filename or "attachment").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".csv", ".txt", ".zip"}:
        raise HTTPException(422, "不支持此附件类型")
    data = await file.read(10*1024*1024+1)
    if not data or len(data) > 10*1024*1024:
        raise HTTPException(422, "附件须为1字节至10MB")
    FILES.mkdir(exist_ok=True)
    filename = uuid4().hex + suffix
    path = FILES / filename
    path.write_bytes(data)
    item = QuotationAttachment(rfq_id=rfq_id, supplier_id=account.supplier_id, name=name[:200], storage_name=filename, size=len(data))
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(409, "附件保存失败，请重试") from None
    return {"id": item.id, "name": item.name, "size": item.size}


def owned_attachment(db, rfq_id, attachment_id, account):
    invitation_for(db, rfq_id, account)
    item = db.get(QuotationAttachment, attachment_id)
    if not item or item.rfq_id != rfq_id or item.supplier_id != account.supplier_id:
        raise HTTPException(404, "附件不存在")
    return item


@router.delete("/supplier/rfqs/{rfq_id}/quotation-attachments/{attachment_id}", status_code=204)
def delete_quote_attachment(rfq_id: str, attachment_id: str, account=Depends(supplier_user), db: Session = Depends(get_db)):
    item = owned_attachment(db, rfq_id, attachment_id, account)
    rfq, invitation = invitation_for(db, rfq_id, account)
    require_open_quote_for(db, rfq, invitation)
    if item.quotation_id:
        raise HTTPException(409, "已提交附件不可删除")
    path = FILES / item.storage_name
    db.delete(item)
    db.commit()
    path.unlink(missing_ok=True)


def quote_attachment_response(item):
    path = FILES / item.storage_name
    if not path.is_file():
        raise HTTPException(404, "附件文件不存在")
    return FileResponse(path, filename=item.name, media_type="application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})


@router.get("/supplier/rfqs/{rfq_id}/quotation-attachments/{attachment_id}")
def download_own_quote_attachment(rfq_id: str, attachment_id: str, account=Depends(supplier_user), db: Session = Depends(get_db)):
    return quote_attachment_response(owned_attachment(db, rfq_id, attachment_id, account))


@router.post("/supplier/rfqs/{rfq_id}/quotation-attachments/{attachment_id}/extract")
def extract_quote_attachment(rfq_id: str, attachment_id: str, account=Depends(supplier_user), db: Session = Depends(get_db)):
    item = owned_attachment(db, rfq_id, attachment_id, account)
    rfq, invitation = invitation_for(db, rfq_id, account)
    require_open_quote_for(db, rfq, invitation)
    path = FILES / item.storage_name
    if not path.is_file():
        raise HTTPException(404, "附件文件不存在")
    try:
        if Path(item.name).suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}:
            result = extract_visual_quotation(path.read_bytes(), item.name, rfq.lines, effective_ai_config(db))
        else:
            result = parse_quotation(path.read_bytes(), item.name, rfq.lines)
            result["extraction_mode"] = "structured"
    except (ValueError, VisionExtractionError) as exc:
        raise HTTPException(422, str(exc)) from exc
    write_audit_log(db, actor_id=account.id, actor_role="supplier", action="extract", resource_type="quotation_attachment", resource_id=item.id, detail=f"识别报价附件 {item.name}，匹配率 {result['confidence']:.0%}")
    db.commit()
    return result


@router.get("/rfqs/{rfq_id}/quotation-attachments/{attachment_id}", dependencies=[Depends(editor)])
def buyer_quote_attachment(rfq_id: str, attachment_id: str, db: Session = Depends(get_db)):
    item = db.get(QuotationAttachment, attachment_id)
    if not item or item.rfq_id != rfq_id or not item.quotation_id:
        raise HTTPException(404, "附件不存在或尚未随报价提交")
    return quote_attachment_response(item)


class MailInput(BaseModel):
    host: str = Field(max_length=200)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(default="", max_length=200)
    password: str | None = Field(default=None, max_length=1000)
    from_email: str = Field(max_length=200)
    security: str = Field(default="starttls", pattern="^(starttls|ssl)$")
    portal_url: str = Field(max_length=500)
    auto_send: bool = False

    @field_validator("host", "from_email", "portal_url")
    @classmethod
    def no_newlines(cls, value):
        if any(c in value for c in "\r\n"):
            raise ValueError("不能包含换行")
        return value


@router.get("/mail-settings", dependencies=[Depends(manager)])
def mail_settings(db: Session = Depends(get_db)):
    item = db.get(MailSettings, 1)
    if not item:
        return {"host": "", "port": 587, "username": "", "from_email": "", "security": "starttls", "portal_url": "http://localhost:8080/supplier", "auto_send": False, "password_set": False}
    return {**{field: getattr(item, field) for field in MailInput.model_fields if field != "password"}, "password_set": bool(item.password_encrypted)}


@router.put("/mail-settings", dependencies=[Depends(manager)])
def save_mail(payload: MailInput, db: Session = Depends(get_db), user=Depends(manager)):
    if payload.auto_send and (not payload.host or "@" not in payload.from_email or not payload.portal_url.startswith(("https://", "http://"))):
        raise HTTPException(422, "自动发送需要完整SMTP、发件邮箱和供应商门户地址")
    item = db.get(MailSettings, 1) or MailSettings(id=1)
    for key, value in payload.model_dump(exclude={"password"}).items():
        setattr(item, key, value)
    if payload.password:
        item.password_encrypted = cipher().encrypt(payload.password.encode()).decode()
    db.add(item)
    write_audit_log(db, actor_id=user.user_id, actor_role=user.role, action="update", resource_type="mail_settings", resource_id="1", detail="更新SMTP及询价自动通知设置（不记录授权码）")
    db.commit()
    return mail_settings(db)


@router.post("/rfqs/{rfq_id}/send-mail", dependencies=[Depends(editor)])
def send_mail(rfq_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    rfq = rfq_service.get(db, rfq_id)
    settings = db.get(MailSettings, 1)
    if not rfq or rfq.status != "published":
        raise HTTPException(409, "只有已发布询价可以发送")
    if not settings or not settings.host or not settings.from_email:
        raise HTTPException(409, "请先配置邮件发送设置")
    queue_invitations(db, rfq)
    # Refresh failed recipients after supplier email correction; sent rows never resend.
    for item in db.scalars(select(RFQMail).where(RFQMail.rfq_id == rfq_id, RFQMail.status.in_(["pending", "failed"]))):
        supplier = db.scalar(select(SupplierRecord).where(or_(SupplierRecord.id == item.supplier_id, SupplierRecord.code == item.supplier_id)))
        item.recipient = supplier.email if supplier else ""
    db.commit()
    tasks.add_task(dispatch_rfq, rfq_id)
    return {"status": "queued"}
