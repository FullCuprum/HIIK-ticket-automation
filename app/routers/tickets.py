from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.redis_client import get_clarification_service
from app.models.ticket import Ticket
from app.schemas.ticket import (
    ClarificationRequest,
    ClarificationResponse,
    TicketCreate,
    TicketResponse,
)
from app.services.clarification import ClarificationService
from app.services.parser import get_ticket_parser
from app.services.scheduler import schedule_ticket

router = APIRouter(prefix="/tickets", tags=["tickets"])

ALLOWED_ANSWER_FIELDS = {
    "location",
    "problem_description",
    "ticket_type",
    "priority",
    "estimated_minutes",
    "required_skill",
}


def _parsed_to_extracted(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "location": parsed.get("location"),
        "problem_description": parsed.get("problem_description"),
        "ticket_type": parsed.get("ticket_type"),
        "priority": parsed.get("priority"),
        "estimated_minutes": parsed.get("estimated_minutes"),
        "required_skill": parsed.get("required_skill"),
    }


def _apply_extracted_to_ticket(ticket: Ticket, extracted: dict[str, Any]) -> None:
    ticket.extracted_location = extracted.get("location")
    ticket.extracted_problem = extracted.get("problem_description")
    ticket.ticket_type = extracted.get("ticket_type")
    ticket.priority = extracted.get("priority", "low")
    ticket.estimated_minutes = extracted.get("estimated_minutes")
    ticket.required_skill = extracted.get("required_skill")


def _build_ticket_response(
    ticket: Ticket,
    missing_fields: list[str],
    questions: list[str] | None = None,
) -> TicketResponse:
    return TicketResponse(
        id=ticket.id,
        raw_text=ticket.raw_text,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        session_id=ticket.id,
        missing_fields=missing_fields,
        questions=questions or [],
        extracted_location=ticket.extracted_location,
        extracted_problem=ticket.extracted_problem,
        ticket_type=ticket.ticket_type,
        priority=ticket.priority,
        estimated_minutes=ticket.estimated_minutes,
        required_skill=ticket.required_skill,
    )


def _normalize_answer_value(field: str, value: Any) -> Any:
    if field == "estimated_minutes":
        return int(value)
    if isinstance(value, str):
        return value.strip()
    return value


def _filter_answers(answers: dict[str, Any], missing_fields: list[str]) -> dict[str, Any]:
    filtered: dict[str, Any] = {}
    for field in missing_fields:
        if field not in answers or field not in ALLOWED_ANSWER_FIELDS:
            continue
        value = answers[field]
        if value is None:
            continue
        filtered[field] = _normalize_answer_value(field, value)
    return filtered


async def _finalize_ready_ticket(db: AsyncSession, ticket: Ticket) -> None:
    """Создаёт слот расписания и предложение на утверждение."""
    result = await schedule_ticket(db, ticket)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail="Ticket is ready, but scheduling failed due to missing employees.",
        )


@router.post("/", response_model=TicketResponse)
async def create_ticket(
    ticket_data: TicketCreate,
    db: AsyncSession = Depends(get_db),
    clarification_service: ClarificationService = Depends(get_clarification_service),
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

    extracted = ClarificationService.fill_derived_fields(_parsed_to_extracted(parsed))
    missing_fields = ClarificationService.compute_missing_fields(extracted)
    _apply_extracted_to_ticket(ticket, extracted)

    questions: list[str] = []
    if missing_fields:
        ticket.status = "need_clarification"
        try:
            await clarification_service.create_session(ticket.id, extracted, missing_fields)
            questions = clarification_service.generate_questions(missing_fields)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=500,
                detail="Ticket saved, but failed to create clarification session.",
            ) from exc
    else:
        ticket.status = "ready_for_scheduling"
        await _finalize_ready_ticket(db, ticket)

    try:
        await db.commit()
        await db.refresh(ticket)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Ticket saved, but failed to update parsed fields.",
        ) from exc

    return _build_ticket_response(ticket, missing_fields, questions)


@router.post("/{ticket_id}/clarify", response_model=ClarificationResponse)
async def clarify_ticket(
    ticket_id: int,
    payload: ClarificationRequest,
    db: AsyncSession = Depends(get_db),
    clarification_service: ClarificationService = Depends(get_clarification_service),
) -> ClarificationResponse:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.status not in {"need_clarification", "new"}:
        raise HTTPException(
            status_code=400,
            detail=f"Ticket is not awaiting clarification (status={ticket.status}).",
        )

    try:
        session = await clarification_service.get_session(ticket_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Failed to read clarification session.") from exc

    if session is None:
        raise HTTPException(status_code=404, detail="Clarification session not found.")

    missing_fields = session.get("missing_fields", [])
    if not payload.answers:
        raise HTTPException(status_code=400, detail="Answers must not be empty.")

    filtered_answers = _filter_answers(payload.answers, missing_fields)
    if not filtered_answers:
        raise HTTPException(
            status_code=400,
            detail="No valid answers provided for missing fields.",
        )

    try:
        updated_session = await clarification_service.update_session(ticket_id, filtered_answers)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Failed to update clarification session.") from exc

    extracted = updated_session["extracted"]
    missing_fields = updated_session["missing_fields"]
    questions = clarification_service.generate_questions(missing_fields)
    _apply_extracted_to_ticket(ticket, extracted)

    if not missing_fields:
        ticket.status = "ready_for_scheduling"
        await _finalize_ready_ticket(db, ticket)
        try:
            await clarification_service.delete_session(ticket_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail="Failed to delete clarification session.") from exc
    else:
        ticket.status = "need_clarification"

    try:
        await db.commit()
        await db.refresh(ticket)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update ticket.") from exc

    return ClarificationResponse(
        ticket_id=ticket.id,
        status=ticket.status,
        missing_fields=missing_fields,
        questions=questions,
        extracted=extracted,
    )
