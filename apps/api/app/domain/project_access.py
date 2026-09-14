from datetime import date
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, model_validator
from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProjectGrant(Base):
    __tablename__ = 'project_staff_grants'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    staff_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)


class GrantInput(BaseModel):
    project_id: str
    staff_id: str
    role: Literal['viewer', 'planner']
    valid_from: date
    valid_to: date

    @model_validator(mode='after')
    def period(self):
        if self.valid_to < self.valid_from:
            raise ValueError('授权结束日期不能早于开始日期')
        return self
