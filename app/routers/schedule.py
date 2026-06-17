from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.ticket import Ticket
from app.schemas.common import MessageResponse
from app.schemas.schedule import (
    ApprovalActionRequest,
    ApprovalItemResponse,
    ScheduleEmployeeOption,
    ScheduleItemResponse,
)
from app.utils.datetime_utils import local_day_range, local_today

router = APIRouter(prefix="/schedule", tags=["schedule"])


async def _get_ticket_for_schedule(db: AsyncSession, schedule: Schedule) -> Ticket | None:
    return await db.get(Ticket, schedule.ticket_id)


@router.get("/employees", response_model=list[ScheduleEmployeeOption])
async def list_schedule_employees(
    db: AsyncSession = Depends(get_db),
) -> list[ScheduleEmployeeOption]:
    result = await db.execute(
        select(Employee)
        .where(Employee.is_active.is_(True))
        .order_by(Employee.full_name)
    )
    return [
        ScheduleEmployeeOption(id=employee.id, full_name=employee.full_name)
        for employee in result.scalars().all()
    ]


@router.get("/current", response_model=list[ScheduleItemResponse])
async def get_current_schedule(
    schedule_date: date | None = Query(
        default=None,
        description="Дата расписания (по умолчанию — сегодня в часовом поясе системы)",
    ),
    employee_name: str | None = Query(
        default=None,
        description="Фильтр по ФИО сотрудника",
    ),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduleItemResponse]:
    target_day = schedule_date or local_today()
    start_of_day, end_of_day = local_day_range(target_day)

    query = (
        select(Schedule, Ticket, Employee, Approval)
        .join(Ticket, Schedule.ticket_id == Ticket.id)
        .join(Employee, Schedule.employee_id == Employee.id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            Schedule.start_time >= start_of_day,
            Schedule.start_time < end_of_day,
            Approval.status.in_(["pending", "approved"]),
        )
        .order_by(Schedule.start_time)
    )
    if employee_name:
        query = query.where(Employee.full_name == employee_name.strip())

    result = await db.execute(query)
    rows = result.all()

    return [
        ScheduleItemResponse(
            id=schedule.id,
            ticket_id=schedule.ticket_id,
            employee_id=schedule.employee_id,
            employee_name=employee.full_name,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            slot_type=schedule.slot_type,
            description=ticket.extracted_problem or ticket.raw_text,
            location=ticket.extracted_location,
        )
        for schedule, ticket, employee, _approval in rows
    ]


@router.get("/approvals", response_model=list[ApprovalItemResponse])
async def list_schedule_approvals(
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalItemResponse]:
    query = (
        select(Approval, Schedule, Ticket, Employee)
        .join(Schedule, Approval.proposed_schedule_id == Schedule.id)
        .join(Ticket, Schedule.ticket_id == Ticket.id)
        .join(Employee, Schedule.employee_id == Employee.id)
        .where(Approval.status == "pending")
        .order_by(Approval.created_at.desc())
    )
    result = await db.execute(query)
    rows = result.all()

    return [
        ApprovalItemResponse(
            id=approval.id,
            ticket_id=schedule.ticket_id,
            proposed_schedule_id=approval.proposed_schedule_id,
            status=approval.status,
            description=ticket.extracted_problem or ticket.raw_text,
            location=ticket.extracted_location,
            employee_name=employee.full_name,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            created_at=approval.created_at,
        )
        for approval, schedule, ticket, employee in rows
    ]


@router.post("/approvals/{approval_id}/approve", response_model=MessageResponse)
async def approve_schedule_item(
    approval_id: int,
    payload: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    approval = await db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="Approval already processed")

    schedule = await db.get(Schedule, approval.proposed_schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule slot not found")

    ticket = await _get_ticket_for_schedule(db, schedule)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    approval.status = "approved"
    approval.manager_comment = payload.manager_comment
    ticket.status = "approved"

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to approve item") from exc

    return MessageResponse(message="Approval accepted")


@router.post("/approvals/{approval_id}/reject", response_model=MessageResponse)
async def reject_schedule_item(
    approval_id: int,
    payload: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    approval = await db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="Approval already processed")

    schedule = await db.get(Schedule, approval.proposed_schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule slot not found")

    ticket = await _get_ticket_for_schedule(db, schedule)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    approval.status = "rejected"
    approval.manager_comment = payload.manager_comment
    ticket.status = "rejected"

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to reject item") from exc

    return MessageResponse(message="Approval rejected")


@router.post("/rebuild", response_model=MessageResponse)
async def rebuild_schedule() -> MessageResponse:
    return MessageResponse(message="schedule rebuild requested")
