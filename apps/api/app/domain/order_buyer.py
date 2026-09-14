from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrderBuyerAssignment(Base):
    __tablename__ = "order_buyer_assignments"
    order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), primary_key=True)
    buyer_id: Mapped[str] = mapped_column(ForeignKey("staff_users.id"), index=True)
    assigned_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
