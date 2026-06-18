from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    raw_text: str = Field(..., min_length=1, description="Ticket text in free form.")
    extracted: dict[str, Any] | None = Field(
        default=None,
        description="Уточнённые поля заявки после предпросмотра.",
    )


class TicketPreviewClarifyRequest(BaseModel):
    raw_text: str = Field(..., min_length=1)
    extracted: dict[str, Any] = Field(default_factory=dict)
    answers: dict[str, Any] = Field(default_factory=dict)


class TicketPreviewResponse(BaseModel):
    raw_text: str
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    extracted: dict[str, Any] = Field(default_factory=dict)


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_text: str
    status: str
    created_at: datetime
    updated_at: datetime
    session_id: int
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    extracted_location: str | None = None
    extracted_building: str | None = None
    extracted_problem: str | None = None
    ticket_type: str | None = None
    priority: str = "low"
    estimated_minutes: int | None = None
    required_skill: str | None = None
    event_datetime: datetime | None = None


class ClarificationRequest(BaseModel):
    answers: dict[str, Any] = Field(
        ...,
        description="Ответы пользователя по недостающим полям.",
        examples=[{"location": "214", "problem_description": "не работает интернет"}],
    )


class ClarificationResponse(BaseModel):
    ticket_id: int
    status: str
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    extracted: dict[str, Any] = Field(default_factory=dict)


class TicketJournalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_text: str
    status: str
    created_at: datetime
    updated_at: datetime
    creator_username: str | None = None
    extracted_location: str | None = None
    extracted_building: str | None = None
    extracted_problem: str | None = None
    ticket_type: str | None = None
    priority: str = "low"
    estimated_minutes: int | None = None
    event_datetime: datetime | None = None
    approval_status: str | None = None
    manager_comment: str | None = None
    completed_at: datetime | None = None
