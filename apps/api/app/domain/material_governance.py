from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MaterialDuplicateDecisionRecord(Base):
    __tablename__ = "material_duplicate_decisions"
    __table_args__ = (UniqueConstraint("left_material_id", "right_material_id", name="uq_material_duplicate_pair"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    left_material_id: Mapped[str] = mapped_column(String(36), index=True)
    right_material_id: Mapped[str] = mapped_column(String(36), index=True)
    similarity: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="watchlist", index=True)
    master_material_id: Mapped[str] = mapped_column(String(36), default="")
    basis: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(64), default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
