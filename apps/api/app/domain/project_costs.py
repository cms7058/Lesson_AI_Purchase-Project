from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProjectAllocation(Base):
    __tablename__ = 'project_purchase_allocations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    task_id: Mapped[str] = mapped_column(String(64), default='')
    line_id: Mapped[int] = mapped_column(Integer, index=True)
    order_id: Mapped[str] = mapped_column(String(36), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))


class AllocationInput(BaseModel):
    line_id: int
    task_id: str = ''
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
