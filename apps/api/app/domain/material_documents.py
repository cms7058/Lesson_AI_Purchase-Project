from datetime import date, datetime
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MaterialTechnicalDocumentRecord(Base):
    __tablename__ = "material_technical_documents"
    __table_args__ = (UniqueConstraint("material_id", "document_no", "version", name="uq_material_document_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    material_id: Mapped[str] = mapped_column(String(36), index=True)
    document_no: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(200))
    document_type: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    file_name: Mapped[str] = mapped_column(String(240))
    storage_name: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    reviewed_by: Mapped[str] = mapped_column(String(64), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MaterialDocumentEventRecord(Base):
    __tablename__ = "material_technical_document_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaterialDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    document_type: str | None = Field(default=None, pattern="^(drawing|specification|inspection_standard|certificate|process_instruction|other)$")
    effective_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)


class MaterialDocumentDecision(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=1000)
