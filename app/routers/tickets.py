from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.ticket import Ticket
from app.schemas.ticket import TicketCreate, TicketResponse
from app.services.parser import get_ticket_parser

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _build_ticket_response(ticket: Ticket, missing_fields: list[str]) -> TicketResponse:
    return TicketResponse(
        id=ticket.id,
        raw_text=ticket.raw_text,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        session_id=ticket.id,
        missing_fields=missing_fields,
        extracted_location=ticket.extracted_location,
        extracted_problem=ticket.extracted_problem,
        ticket_type=ticket.ticket_type,
        priority=ticket.priority,
        estimated_minutes=ticket.estimated_minutes,
        required_skill=ticket.required_skill,
    )


def _apply_parsed_fields(ticket: Ticket, parsed: dict) -> None:
    ticket.extracted_location = parsed.get("location")
    ticket.extracted_problem = parsed.get("problem_description")
    ticket.ticket_type = parsed.get("ticket_type")
    ticket.priority = parsed.get("priority", "low")
    ticket.estimated_minutes = parsed.get("estimated_minutes")
    ticket.required_skill = parsed.get("required_skill")


@router.post("/", response_model=TicketResponse)
async def create_ticket(
    ticket_data: TicketCreate,
    db: AsyncSession = Depends(get_db),
) -> TicketResponse:
    ticket = Ticket(raw_text=ticket_data.raw_text, status="new")

    try:
        db.add(ticket)
        await db.commit()
        await db.refresh(ticket)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create ticket") from exc

    try:
        parsed = get_ticket_parser().parse(ticket_data.raw_text)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail="Ticket saved, but parsing failed. Status remains 'new'.",
        ) from exc

    missing_fields = parsed.get("missing_fields", [])
    _apply_parsed_fields(ticket, parsed)

    if missing_fields:
        ticket.status = "need_clarification"
    else:
        ticket.status = "ready_for_scheduling"

    try:
        await db.commit()
        await db.refresh(ticket)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Ticket saved, but failed to update parsed fields.",
        ) from exc

    return _build_ticket_response(ticket, missing_fields)
