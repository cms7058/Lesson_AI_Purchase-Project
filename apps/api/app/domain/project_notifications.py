from uuid import uuid4

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProjectNotification(Base):
    __tablename__ = 'project_notifications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_key: Mapped[str] = mapped_column(String(64), unique=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    task_id: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[str] = mapped_column(String(36))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default='open')
    mail_status: Mapped[str] = mapped_column(String(20), default='not_sent')
    recipient: Mapped[str] = mapped_column(String(200), default='')
    error: Mapped[str] = mapped_column(String(300), default='')
    created_at: Mapped[str] = mapped_column(String(40))
