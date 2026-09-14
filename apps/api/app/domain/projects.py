import json
from datetime import date
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProjectRecord(Base):
    __tablename__ = 'managed_projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default='draft')
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[str] = mapped_column(Text)


class ProjectBaseline(Base):
    __tablename__ = 'project_baselines'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    project_version: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40))
    payload: Mapped[str] = mapped_column(Text)


class ProjectTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None
    kind: Literal['work_package', 'task', 'milestone'] = 'task'
    owner_id: str | None = None
    start: date | None = None
    finish: date | None = None
    progress: int = Field(default=0, ge=0, le=100)
    predecessors: list[str] = Field(default_factory=list, max_length=100)
    source: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def dates(self):
        if self.start and self.finish and self.start > self.finish:
            raise ValueError('任务结束日期不能早于开始日期')
        if self.kind == 'milestone' and self.start != self.finish:
            raise ValueError('里程碑开始和结束日期必须相同')
        return self


class ProjectImportEvidence(BaseModel):
    filename: str = Field(default='', max_length=200)
    fingerprint: str = Field(default='', max_length=64)
    engine: str = Field(default='rule-preview-v1', max_length=50)
    source_text: str = Field(default='', max_length=20000)
    warnings: list[str] = Field(default_factory=list, max_length=30)


class ProjectInput(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    manager_id: str | None = None
    status: Literal['draft', 'active', 'completed', 'archived'] = 'draft'
    currency: str = Field(default='CNY', pattern='^[A-Z]{3}$')
    budget: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False)
    description: str = Field(default='', max_length=20000)
    import_evidence: ProjectImportEvidence | None = None
    tasks: list[ProjectTask] = Field(default_factory=list, max_length=500)
    version: int = Field(default=1, ge=1)

    @model_validator(mode='after')
    def graph(self):
        ids = {t.id for t in self.tasks}
        if len(ids) != len(self.tasks):
            raise ValueError('任务编号不能重复')
        for t in self.tasks:
            if any(i not in ids or i == t.id for i in t.predecessors) or (t.parent_id and (t.parent_id not in ids or t.parent_id == t.id)):
                raise ValueError('任务关联无效或关联自身')
        for graph in ({t.id: t.predecessors for t in self.tasks}, {t.id: [t.parent_id] if t.parent_id else [] for t in self.tasks}):
            visited, active = set(), set()
            def visit(node, active=active, visited=visited, graph=graph):
                if node in active:
                    raise ValueError('任务层级或依赖存在循环')
                if node in visited:
                    return
                active.add(node)
                for other in graph[node]:
                    visit(other)
                active.remove(node)
                visited.add(node)
            for key in graph:
                visit(key)
        if self.status == 'active' and (not self.tasks or not self.manager_id or any(not t.start or not t.finish or not t.owner_id for t in self.tasks)):
            raise ValueError('发布前请完善项目经理以及所有任务的日期和负责人')
        if self.status == 'completed' and any(t.progress != 100 for t in self.tasks):
            raise ValueError('任务全部完成后才能完成项目')
        return self


def project_data(record):
    data = json.loads(record.payload)
    return {**data, 'id': record.id, 'version': record.version}
