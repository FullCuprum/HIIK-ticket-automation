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
    ApprovalProposalUpdate,
    ScheduleEmployeeOption,
    ScheduleItemResponse,
)
from app.services.buildings import normalize_building
from app.utils.auth import get_user_by_username, normalize_role
from app.utils.datetime_utils import local_day_range, local_today, now_local
from app.utils.deps import get_optional_auth, require_auth, require_admin

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _proposal_description(ticket: Ticket) -> str | None:
    return ticket.extracted_problem or ticket.raw_text


def _build_schedule_item(
    schedule: Schedule,
    ticket: Ticket,
    employee: Employee,
    approval: Approval | None = None,
    *,
    can_complete: bool = False,
) -> ScheduleItemResponse:
    return ScheduleItemResponse(
        id=schedule.id,
        ticket_id=schedule.ticket_id,
        employee_id=schedule.employee_id,
        employee_name=employee.full_name,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        slot_type=schedule.slot_type,
        description=_proposal_description(ticket),
        location=ticket.extracted_location,
        building=ticket.extracted_building,
        approval_status=approval.status if approval else None,
        manager_comment=approval.manager_comment if approval else None,
        ticket_status=ticket.status,
        completed_at=ticket.completed_at,
        can_complete=can_complete,
        raw_text=ticket.raw_text,
        creator_username=ticket.creator_username,
    )


def _build_approval_item(
    approval: Approval,
    schedule: Schedule,
    ticket: Ticket,
    employee: Employee,
) -> ApprovalItemResponse:
    return ApprovalItemResponse(
        id=approval.id,
        ticket_id=schedule.ticket_id,
        proposed_schedule_id=approval.proposed_schedule_id,
        employee_id=schedule.employee_id,
        status=approval.status,
        description=_proposal_description(ticket),
        location=ticket.extracted_location,
        building=ticket.extracted_building,
        employee_name=employee.full_name,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        raw_text=ticket.raw_text,
        creator_username=ticket.creator_username,
        created_at=approval.created_at,
    )


async def _get_employee_id_for_user(db: AsyncSession, username: str) -> int | None:
    user = await get_user_by_username(db, username)
    if user is None:
        return None
    result = await db.execute(select(Employee.id).where(Employee.user_id == user.id).limit(1))
    return result.scalar_one_or_none()


def _can_complete_ticket(
    ticket: Ticket,
    approval: Approval | None,
    schedule: Schedule,
    *,
    role: str,
    user_employee_id: int | None,
) -> bool:
    if ticket.status != "approved" or approval is None or approval.status != "approved":
        return False
    if role == "admin":
        return True
    if role == "employee" and user_employee_id is not None:
        return schedule.employee_id == user_employee_id
    return False


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
    auth: dict | None = Depends(get_optional_auth),
) -> list[ScheduleItemResponse]:
    target_day = schedule_date or local_today()
    start_of_day, end_of_day = local_day_range(target_day)

    role = ""
    user_employee_id: int | None = None
    if auth:
        role = normalize_role(auth.get("role", ""))
        username = auth.get("sub")
        if role == "employee" and username:
            user_employee_id = await _get_employee_id_for_user(db, username)

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
        _build_schedule_item(
            schedule,
            ticket,
            employee,
            approval,
            can_complete=_can_complete_ticket(
                ticket,
                approval,
                schedule,
                role=role,
                user_employee_id=user_employee_id,
            ),
        )
        for schedule, ticket, employee, approval in rows
    ]


@router.post("/{schedule_id}/complete", response_model=ScheduleItemResponse)
async def complete_schedule_item(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> ScheduleItemResponse:
    schedule = await db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule item not found")

    ticket = await _get_ticket_for_schedule(db, schedule)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    approval_result = await db.execute(
        select(Approval).where(Approval.proposed_schedule_id == schedule.id).limit(1)
    )
    approval = approval_result.scalar_one_or_none()

    role = normalize_role(auth.get("role", ""))
    if role not in {"admin", "employee"}:
        raise HTTPException(status_code=403, detail="Access denied")

    username = auth.get("sub")
    user_employee_id = await _get_employee_id_for_user(db, username) if username else None

    if not _can_complete_ticket(
        ticket,
        approval,
        schedule,
        role=role,
        user_employee_id=user_employee_id,
    ):
        raise HTTPException(status_code=403, detail="You cannot complete this ticket")

    if ticket.status == "completed":
        raise HTTPException(status_code=400, detail="Ticket is already completed")

    ticket.status = "completed"
    ticket.completed_at = now_local()

    try:
        await db.commit()
        await db.refresh(schedule)
        await db.refresh(ticket)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to complete ticket") from exc

    employee = await db.get(Employee, schedule.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    return _build_schedule_item(schedule, ticket, employee, approval, can_complete=False)


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
        _build_approval_item(approval, schedule, ticket, employee)
        for approval, schedule, ticket, employee in rows
    ]


@router.put("/approvals/{approval_id}", response_model=ApprovalItemResponse)
async def update_schedule_approval(
    approval_id: int,
    payload: ApprovalProposalUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> ApprovalItemResponse:
    approval = await db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending approvals can be edited")

    schedule = await db.get(Schedule, approval.proposed_schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule slot not found")

    ticket = await _get_ticket_for_schedule(db, schedule)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "description" in update_data:
        ticket.extracted_problem = update_data["description"]

    if "location" in update_data:
        ticket.extracted_location = update_data["location"]

    if "building" in update_data:
        normalized_building = normalize_building(update_data["building"])
        if normalized_building is None:
            raise HTTPException(status_code=400, detail="Invalid building value")
        ticket.extracted_building = normalized_building

    if "employee_id" in update_data:
        employee = await db.get(Employee, update_data["employee_id"])
        if employee is None or not employee.is_active:
            raise HTTPException(status_code=400, detail="Employee not found or inactive")
        schedule.employee_id = employee.id

    if "start_time" in update_data:
        schedule.start_time = update_data["start_time"]
    if "end_time" in update_data:
        schedule.end_time = update_data["end_time"]

    if schedule.end_time <= schedule.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    try:
        await db.commit()
        await db.refresh(schedule)
        await db.refresh(ticket)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update approval proposal") from exc

    employee = await db.get(Employee, schedule.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    return _build_approval_item(approval, schedule, ticket, employee)


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
