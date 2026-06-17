from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    extracted_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted_building: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extracted_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    required_skill: Mapped[str | None] = mapped_column(String(100), nullable=True)
    creator_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
