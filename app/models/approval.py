from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    proposed_schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedule_slots.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    manager_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
