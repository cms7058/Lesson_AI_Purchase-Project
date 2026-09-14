from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplierAccount(Base):
    __tablename__ = "supplier_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    supplier_id: Mapped[str] = mapped_column(String(36), unique=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SupplierSession(Base):
    __tablename__ = "supplier_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class RFQAttachment(Base):
    __tablename__ = "rfq_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    rfq_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    storage_name: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)


class SupplierSubmission(Base):
    __tablename__ = "supplier_submissions"
    __table_args__ = (UniqueConstraint("rfq_id", "supplier_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    rfq_id: Mapped[str] = mapped_column(String(36), index=True)
    supplier_id: Mapped[str] = mapped_column(String(36))
    quotation_id: Mapped[str] = mapped_column(String(36), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class QuotationReview(Base):
    __tablename__ = "quotation_reviews"
    quotation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rfq_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewer_id: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuotationAttachment(Base):
    __tablename__ = "supplier_quotation_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    rfq_id: Mapped[str] = mapped_column(String(36), index=True)
    supplier_id: Mapped[str] = mapped_column(String(36), index=True)
    quotation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    storage_name: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)


class MailSettings(Base):
    __tablename__ = "mail_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    host: Mapped[str] = mapped_column(String(200), default="")
    port: Mapped[int] = mapped_column(Integer, default=587)
    username: Mapped[str] = mapped_column(String(200), default="")
    password_encrypted: Mapped[str] = mapped_column(Text, default="")
    from_email: Mapped[str] = mapped_column(String(200), default="")
    security: Mapped[str] = mapped_column(String(20), default="starttls")
    portal_url: Mapped[str] = mapped_column(String(500), default="http://localhost:8080/supplier")
    auto_send: Mapped[bool] = mapped_column(Boolean, default=False)


class AIModelSettings(Base):
    __tablename__ = "ai_model_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str] = mapped_column(String(50), default="openai_compatible")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(200), default="")
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")


class RFQMail(Base):
    __tablename__ = "rfq_mails"
    __table_args__ = (UniqueConstraint("rfq_id", "supplier_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    rfq_id: Mapped[str] = mapped_column(String(36), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64))
    recipient: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str] = mapped_column(String(300), default="")
