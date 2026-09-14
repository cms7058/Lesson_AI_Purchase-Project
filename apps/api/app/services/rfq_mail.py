import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import or_, select, update

from app.core.database import SessionLocal
from app.domain.persistence import RFQRecord, SupplierRecord
from app.domain.supplier_portal import MailSettings, RFQMail


def cipher():
    # Keep the old variable as a compatibility fallback for existing deployments.
    key = os.environ.get("AI_ASSIST_SECRET_KEY") or os.environ.get("PEBS_SECRET_KEY")
    if not key:
        path = Path(".mail-secret.key")
        if not path.exists():
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as file:
                    file.write(Fernet.generate_key())
            except FileExistsError:
                pass
        key = path.read_bytes()
    return Fernet(key)


def queue_invitations(db, rfq):
    for invitation in rfq.invitations:
        existing = db.scalar(select(RFQMail).where(RFQMail.rfq_id == rfq.id, RFQMail.supplier_id == invitation.supplier_id))
        if existing:
            continue
        supplier = db.scalar(select(SupplierRecord).where(or_(SupplierRecord.id == invitation.supplier_id, SupplierRecord.code == invitation.supplier_id)))
        db.add(RFQMail(rfq_id=rfq.id, supplier_id=invitation.supplier_id, recipient=supplier.email if supplier else ""))


def dispatch_rfq(rfq_id):
    with SessionLocal() as db:
        settings = db.get(MailSettings, 1)
        if not settings or not settings.host or not settings.from_email:
            return
        rfq = db.get(RFQRecord, rfq_id)
        if not rfq or rfq.status != "published":
            return
        ids = list(db.scalars(select(RFQMail.id).where(RFQMail.rfq_id == rfq_id, RFQMail.status.in_(["pending", "failed"]))))
        for item_id in ids:
            claimed = db.execute(update(RFQMail).where(RFQMail.id == item_id, RFQMail.status.in_(["pending", "failed"])).values(status="sending", error=""))
            db.commit()
            if not claimed.rowcount:
                continue
            item = db.get(RFQMail, item_id)
            try:
                if not item.recipient or "@" not in item.recipient or any(c in item.recipient for c in "\r\n"):
                    raise ValueError("供应商邮箱未配置或格式错误")
                msg = EmailMessage()
                msg["From"] = settings.from_email
                msg["To"] = item.recipient
                msg["Subject"] = f"采购询价邀请 {rfq.rfq_no} · {rfq.title}"
                msg.set_content(f"您收到新的询价邀请：{rfq.title}\n编号：{rfq.rfq_no}\n截止日期：{rfq.deadline or '未设置'}\n请使用采购方提供的供应商账号登录：{settings.portal_url}\n登录后查看物料及附件并提交报价。请勿通过回复此邮件报价。")
                factory = smtplib.SMTP_SSL if settings.security == "ssl" else smtplib.SMTP
                options = {"context": ssl.create_default_context()} if settings.security == "ssl" else {}
                with factory(settings.host, settings.port, timeout=15, **options) as server:
                    if settings.security == "starttls":
                        server.starttls(context=ssl.create_default_context())
                    if settings.username:
                        password = cipher().decrypt(settings.password_encrypted.encode()).decode() if settings.password_encrypted else ""
                        server.login(settings.username, password)
                    server.send_message(msg)
                item.status = "sent"
            except (OSError, smtplib.SMTPException, ValueError, InvalidToken):
                # SMTP errors can contain credentials/server responses; do not expose them.
                item.status = "failed"
                item.error = "发送失败，请检查供应商邮箱、SMTP 配置及网络后重试"
            db.commit()
