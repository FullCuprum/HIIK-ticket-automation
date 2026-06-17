from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.schemas.employee import EmployeeCreate, EmployeeListResponse, EmployeeResponse, EmployeeUpdate
from app.utils.auth import decode_access_token
from app.utils.datetime_utils import local_day_range, local_today

router = APIRouter(prefix="/employees", tags=["employees"])

SKILL_OPTIONS = [
    "network_engineer",
    "hardware_support",
    "software_admin",
    "event_support",
    "general_support",
]


async def require_manager(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")

    payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") != "manager":
        raise HTTPException(status_code=403, detail="Manager access required")
    return payload


def _work_minutes_per_day(employee: Employee) -> int:
    return max(employee.work_end_hour - employee.work_start_hour, 0) * 60


async def _get_scheduled_minutes_today(db: AsyncSession, employee_id: int) -> tuple[int, int]:
    today = local_today()
    start_of_day, end_of_day = local_day_range(today)

    result = await db.execute(
        select(Schedule, Approval)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            Schedule.employee_id == employee_id,
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


def _build_employee_response(
    employee: Employee,
    scheduled_minutes: int,
    tasks_today: int,
) -> EmployeeResponse:
    work_minutes = _work_minutes_per_day(employee)
    workload_percent = round((scheduled_minutes / work_minutes) * 100, 1) if work_minutes else 0.0

    return EmployeeResponse(
        id=employee.id,
        full_name=employee.full_name,
        position=employee.position,
        skills=employee.skills,
        max_parallel_tasks=employee.max_parallel_tasks,
        is_active=employee.is_active,
        work_start_hour=employee.work_start_hour,
        work_end_hour=employee.work_end_hour,
        phone=employee.phone,
        email=employee.email,
        work_minutes_per_day=work_minutes,
        scheduled_minutes_today=scheduled_minutes,
        workload_percent=workload_percent,
        tasks_today=tasks_today,
    )


@router.get("/", response_model=EmployeeListResponse)
async def list_employees(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_manager),
) -> EmployeeListResponse:
    result = await db.execute(select(Employee).order_by(Employee.full_name))
    employees = list(result.scalars().all())

    items: list[EmployeeResponse] = []
    for employee in employees:
        scheduled_minutes, tasks_today = await _get_scheduled_minutes_today(db, employee.id)
        items.append(_build_employee_response(employee, scheduled_minutes, tasks_today))

    active_items = [item for item in items if item.is_active]
    average = (
        round(sum(item.workload_percent for item in active_items) / len(active_items), 1)
        if active_items
        else 0.0
    )
    return EmployeeListResponse(items=items, average_workload_percent=average)


@router.get("/skills", response_model=list[str])
async def list_skill_options(_: dict = Depends(require_manager)) -> list[str]:
    return SKILL_OPTIONS


@router.post("/", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    payload: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_manager),
) -> EmployeeResponse:
    employee = Employee(**payload.model_dump())
    db.add(employee)

    try:
        await db.commit()
        await db.refresh(employee)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create employee") from exc

    scheduled_minutes, tasks_today = await _get_scheduled_minutes_today(db, employee.id)
    return _build_employee_response(employee, scheduled_minutes, tasks_today)


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_manager),
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

    try:
        await db.commit()
        await db.refresh(employee)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update employee") from exc

    scheduled_minutes, tasks_today = await _get_scheduled_minutes_today(db, employee.id)
    return _build_employee_response(employee, scheduled_minutes, tasks_today)


@router.delete("/{employee_id}", response_model=EmployeeResponse)
async def deactivate_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_manager),
) -> EmployeeResponse:
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee.is_active = False

    try:
        await db.commit()
        await db.refresh(employee)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to deactivate employee") from exc

    scheduled_minutes, tasks_today = await _get_scheduled_minutes_today(db, employee.id)
    return _build_employee_response(employee, scheduled_minutes, tasks_today)
