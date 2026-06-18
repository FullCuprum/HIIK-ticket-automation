from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.schedule_executor import ScheduleExecutor
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
from app.services.schedule_executors import (
    load_schedule_executor_info,
    set_schedule_executors,
)
from app.utils.auth import get_user_by_username, normalize_role
from app.utils.datetime_utils import local_day_range, local_today, now_local
from app.utils.deps import get_optional_auth, require_auth, require_admin

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _proposal_description(ticket: Ticket) -> str | None:
    return ticket.extracted_problem or ticket.raw_text


def _build_schedule_item(
    schedule: Schedule,
    ticket: Ticket,
    employee_ids: list[int],
    employee_names: list[str],
    employee_name: str,
    approval: Approval | None = None,
    *,
    can_complete: bool = False,
) -> ScheduleItemResponse:
    primary_employee_id = employee_ids[0] if employee_ids else schedule.employee_id
    return ScheduleItemResponse(
        id=schedule.id,
        ticket_id=schedule.ticket_id,
        employee_id=primary_employee_id,
        employee_name=employee_name,
        employee_ids=employee_ids,
        employee_names=employee_names,
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
    employee_ids: list[int],
    employee_names: list[str],
    employee_name: str,
) -> ApprovalItemResponse:
    primary_employee_id = employee_ids[0] if employee_ids else schedule.employee_id
    return ApprovalItemResponse(
        id=approval.id,
        ticket_id=schedule.ticket_id,
        proposed_schedule_id=approval.proposed_schedule_id,
        employee_id=primary_employee_id,
        status=approval.status,
        description=_proposal_description(ticket),
        location=ticket.extracted_location,
        building=ticket.extracted_building,
        employee_name=employee_name,
        employee_ids=employee_ids,
        employee_names=employee_names,
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
    *,
    role: str,
    user_employee_id: int | None,
    executor_ids: list[int],
) -> bool:
    if ticket.status != "approved" or approval is None or approval.status != "approved":
        return False
    if role == "admin":
        return True
    if role == "employee" and user_employee_id is not None:
        return user_employee_id in executor_ids
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
        select(Schedule, Ticket, Approval)
        .join(Ticket, Schedule.ticket_id == Ticket.id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            Schedule.start_time >= start_of_day,
            Schedule.start_time < end_of_day,
            Approval.status.in_(["pending", "approved"]),
        )
        .order_by(Schedule.start_time)
    )
    if employee_name:
        query = (
            query.join(ScheduleExecutor, ScheduleExecutor.schedule_id == Schedule.id)
            .join(Employee, ScheduleExecutor.employee_id == Employee.id)
            .where(Employee.full_name == employee_name.strip())
            .distinct()
        )

    result = await db.execute(query)
    rows = result.all()

    items: list[ScheduleItemResponse] = []
    for schedule, ticket, approval in rows:
        employee_ids, employee_names, employee_name_display = await load_schedule_executor_info(
            db, schedule
        )
        items.append(
            _build_schedule_item(
                schedule,
                ticket,
                employee_ids,
                employee_names,
                employee_name_display,
                approval,
                can_complete=_can_complete_ticket(
                    ticket,
                    approval,
                    role=role,
                    user_employee_id=user_employee_id,
                    executor_ids=employee_ids,
                ),
            )
        )
    return items


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
        role=role,
        user_employee_id=user_employee_id,
        executor_ids=await load_schedule_executor_info(db, schedule)[0],
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

    employee_ids, employee_names, employee_name_display = await load_schedule_executor_info(
        db, schedule
    )
    return _build_schedule_item(
        schedule,
        ticket,
        employee_ids,
        employee_names,
        employee_name_display,
        approval,
        can_complete=False,
    )


@router.get("/approvals", response_model=list[ApprovalItemResponse])
async def list_schedule_approvals(
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalItemResponse]:
    query = (
        select(Approval, Schedule, Ticket)
        .join(Schedule, Approval.proposed_schedule_id == Schedule.id)
        .join(Ticket, Schedule.ticket_id == Ticket.id)
        .where(Approval.status == "pending")
        .order_by(Approval.created_at.desc())
    )
    result = await db.execute(query)
    rows = result.all()

    items: list[ApprovalItemResponse] = []
    for approval, schedule, ticket in rows:
        employee_ids, employee_names, employee_name_display = await load_schedule_executor_info(
            db, schedule
        )
        items.append(
            _build_approval_item(
                approval,
                schedule,
                ticket,
                employee_ids,
                employee_names,
                employee_name_display,
            )
        )
    return items


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

    employee_ids_to_set: list[int] | None = None
    if "employee_ids" in update_data:
        employee_ids_to_set = update_data.get("employee_ids") or []
    elif "employee_id" in update_data:
        employee_id_value = update_data.get("employee_id")
        employee_ids_to_set = [employee_id_value] if employee_id_value is not None else []

    if "start_time" in update_data:
        schedule.start_time = update_data["start_time"]
    if "end_time" in update_data:
        schedule.end_time = update_data["end_time"]

    if schedule.end_time <= schedule.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    if employee_ids_to_set is not None:
        if not employee_ids_to_set:
            raise HTTPException(status_code=400, detail="At least one executor must be selected")

        unique_employee_ids: list[int] = []
        for emp_id in employee_ids_to_set:
            if emp_id not in unique_employee_ids:
                unique_employee_ids.append(emp_id)

        for emp_id in unique_employee_ids:
            employee = await db.get(Employee, emp_id)
            if employee is None or not employee.is_active:
                raise HTTPException(status_code=400, detail="Employee not found or inactive")

        try:
            await set_schedule_executors(db, schedule, unique_employee_ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        await db.commit()
        await db.refresh(schedule)
        await db.refresh(ticket)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update approval proposal") from exc

    employee_ids, employee_names, employee_name_display = await load_schedule_executor_info(
        db, schedule
    )
    return _build_approval_item(
        approval,
        schedule,
        ticket,
        employee_ids,
        employee_names,
        employee_name_display,
    )


@router.post("/approvals/{approval_id}/approve", response_model=MessageResponse)
async def approve_schedule_item(
    approval_id: int,
    payload: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
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
    _: dict = Depends(require_admin),
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
