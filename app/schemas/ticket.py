from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    text: str = Field(..., min_length=1, description="Ticket text in free form.")
