from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    raw_text: str = Field(..., min_length=1, description="Ticket text in free form.")


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_text: str
    status: str
    created_at: datetime
    updated_at: datetime
    session_id: int
    missing_fields: list[str] = Field(default_factory=list)
    extracted_location: str | None = None
    extracted_problem: str | None = None
    ticket_type: str | None = None
    priority: str = "low"
    estimated_minutes: int | None = None
    required_skill: str | None = None
