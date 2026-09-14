from typing import Literal
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class SpareClassification(BaseModel):
    material_type: Literal['production','spare'] = 'production'
    abc: Literal['A','B','C'] = 'B'
    ved: Literal['V','E','D'] = 'E'
    fsn: Literal['F','S','N'] = 'S'
    reason: str = Field(default='',max_length=2000)
    @model_validator(mode='after')
    def evidence(self):
        if self.material_type=='spare' and not self.reason.strip():
            raise ValueError('备件分类必须填写评审依据')
        return self

class MaterialPolicy(Base):
    __tablename__='material_spare_policies'
    material_code: Mapped[str] = mapped_column(String(64),primary_key=True)
    payload: Mapped[str] = mapped_column(Text)

class SpareRequestSnapshot(Base):
    __tablename__='spare_request_snapshots'
    request_id: Mapped[str] = mapped_column(String(36),primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
