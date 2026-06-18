from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.schedule_executor import ScheduleExecutor
from app.models.user import User
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeCreateResponse,
    EmployeeListResponse,
    EmployeeResponse,
    EmployeeUpdate,
)
from app.services.employee_user import (
    create_user_for_employee,
    employee_has_recent_completed_tasks,
    employee_has_scheduled_tasks,
    sync_linked_user,
)
from app.utils.deps import require_admin
from app.utils.datetime_utils import local_day_range, local_today

router = APIRouter(prefix="/employees", tags=["employees"])

SKILL_OPTIONS = [
    "network_engineer",
    "hardware_support",
    "software_admin",
    "event_support",
    "general_support",
]


def _work_minutes_per_day(employee: Employee) -> int:
    return max(employee.work_end_hour - employee.work_start_hour, 0) * 60


async def _get_user_username(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    return user.username if user else None


async def _get_scheduled_minutes_today(db: AsyncSession, employee_id: int) -> tuple[int, int]:
    today = local_today()
    start_of_day, end_of_day = local_day_range(today)

    result = await db.execute(
        select(Schedule, Approval)
        .join(ScheduleExecutor, ScheduleExecutor.schedule_id == Schedule.id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            ScheduleExecutor.employee_id == employee_id,
            Schedule.start_time >= start_of_day,
            Schedule.start_time < end_of_day,
            Approval.status.in_(["pending", "approved"]),
        )
    )

    total_minutes = 0
    tasks_count = 0
    for schedule, _approval in result.all():
        duration = int((schedule.end_time - schedule.start_time).total_seconds() // 60)
        total_minutes += max(duration, 0)
        tasks_count += 1

    return total_minutes, tasks_count


async def _build_employee_response(
    db: AsyncSession,
    employee: Employee,
    scheduled_minutes: int,
    tasks_today: int,
    *,
    initial_password: str | None = None,
) -> EmployeeResponse | EmployeeCreateResponse:
    work_minutes = _work_minutes_per_day(employee)
    workload_percent = round((scheduled_minutes / work_minutes) * 100, 1) if work_minutes else 0.0
    user_username = await _get_user_username(db, employee.user_id)

    response_data = {
        "id": employee.id,
        "full_name": employee.full_name,
        "position": employee.position,
        "skills": employee.skills,
        "max_parallel_tasks": employee.max_parallel_tasks,
        "is_active": employee.is_active,
        "work_start_hour": employee.work_start_hour,
        "work_end_hour": employee.work_end_hour,
        "phone": employee.phone,
        "email": employee.email,
        "user_username": user_username,
        "work_minutes_per_day": work_minutes,
        "scheduled_minutes_today": scheduled_minutes,
        "workload_percent": workload_percent,
        "tasks_today": tasks_today,
    }

    if initial_password is not None:
        return EmployeeCreateResponse(initial_password=initial_password, **response_data)
    return EmployeeResponse(**response_data)


@router.get("/", response_model=EmployeeListResponse)
async def list_employees(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> EmployeeListResponse:
    result = await db.execute(select(Employee).order_by(Employee.full_name))
    employees = list(result.scalars().all())

    items: list[EmployeeResponse] = []
    for employee in employees:
        scheduled_minutes, tasks_today = await _get_scheduled_minutes_today(db, employee.id)
        item = await _build_employee_response(db, employee, scheduled_minutes, tasks_today)
        items.append(item)

    active_items = [item for item in items if item.is_active]
    average = (
        round(sum(item.workload_percent for item in active_items) / len(active_items), 1)
        if active_items
        else 0.0
    )
    return EmployeeListResponse(items=items, average_workload_percent=average)


@router.get("/skills", response_model=list[str])
async def list_skill_options(_: dict = Depends(require_admin)) -> list[str]:
    return SKILL_OPTIONS


@router.post("/", response_model=EmployeeCreateResponse, status_code=201)
async def create_employee(
    payload: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> EmployeeCreateResponse:
    try:
        user, initial_password = await create_user_for_employee(
            db,
            full_name=payload.full_name,
            is_active=payload.is_active,
        )
        employee = Employee(**payload.model_dump(), user_id=user.id)
        db.add(employee)
        await db.commit()
        await db.refresh(employee)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Failed to create employee user account") from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create employee") from exc

    scheduled_minutes, tasks_today = await _get_scheduled_minutes_today(db, employee.id)
    response = await _build_employee_response(
        db,
        employee,
        scheduled_minutes,
        tasks_today,
        initial_password=initial_password,
    )
    return response  # type: ignore[return-value]


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> EmployeeResponse:
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    update_data = payload.model_dump(exclude_unset=True)
    work_start = update_data.get("work_start_hour", employee.work_start_hour)
    work_end = update_data.get("work_end_hour", employee.work_end_hour)
    if work_end <= work_start:
        raise HTTPException(status_code=400, detail="work_end_hour must be greater than work_start_hour")

    for field, value in update_data.items():
        setattr(employee, field, value)

    await sync_linked_user(
        db,
        employee,
        full_name=update_data.get("full_name"),
        is_active=update_data.get("is_active"),
    )

    try:
        await db.commit()
        await db.refresh(employee)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update employee") from exc

    scheduled_minutes, tasks_today = await _get_scheduled_minutes_today(db, employee.id)
    response = await _build_employee_response(db, employee, scheduled_minutes, tasks_today)
    return response  # type: ignore[return-value]


@router.delete("/{employee_id}", status_code=204)
async def delete_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> None:
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    if await employee_has_scheduled_tasks(db, employee_id):
        raise HTTPException(
            status_code=400,
            detail="Невозможно удалить сотрудника с запланированными задачами.",
        )

    if await employee_has_recent_completed_tasks(db, employee_id):
        raise HTTPException(
            status_code=400,
            detail="Невозможно удалить сотрудника с задачами, выполненными за последние 30 дней.",
        )

    linked_user = await db.get(User, employee.user_id) if employee.user_id else None

    await db.delete(employee)
    if linked_user is not None:
        await db.delete(linked_user)

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete employee") from exc
