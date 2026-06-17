from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.ticket import Ticket
from app.services.event_support import EVENT_TOTAL_MINUTES, event_slot_bounds
from app.utils.datetime_utils import local_today, now_local, workday_bounds

logger = logging.getLogger(__name__)

SCHEDULE_BUFFER_MINUTES = 15
MAX_SCHEDULE_LOOKAHEAD_DAYS = 366

DEFAULT_EMPLOYEES = [
    {
        "full_name": "Иванов Иван Иванович",
        "position": "Инженер сетей",
        "skills": ["network_engineer", "hardware_support"],
        "max_parallel_tasks": 2,
        "is_active": True,
        "work_start_hour": 9,
        "work_end_hour": 18,
        "phone": "+7 (900) 111-11-11",
        "email": "ivanov@hiik.sibguti.ru",
    },
    {
        "full_name": "Петров Пётр Петрович",
        "position": "Администратор ПО",
        "skills": ["software_admin", "general_support"],
        "max_parallel_tasks": 2,
        "is_active": True,
        "work_start_hour": 9,
        "work_end_hour": 18,
        "phone": "+7 (900) 222-22-22",
        "email": "petrov@hiik.sibguti.ru",
    },
    {
        "full_name": "Сидоров Сидор Сидорович",
        "position": "Инженер мероприятий",
        "skills": ["network_engineer", "event_support", "general_support"],
        "max_parallel_tasks": 1,
        "is_active": True,
        "work_start_hour": 10,
        "work_end_hour": 19,
        "phone": "+7 (900) 333-33-33",
        "email": "sidorov@hiik.sibguti.ru",
    },
]


def slot_type_for_priority(priority: str) -> str:
    return "high_priority" if priority == "high" else "normal"


async def ensure_default_employees(db: AsyncSession) -> list[Employee]:
    result = await db.execute(select(Employee).where(Employee.is_active.is_(True)))
    employees = list(result.scalars().all())
    if employees:
        return employees

    for employee_data in DEFAULT_EMPLOYEES:
        db.add(Employee(**employee_data))
    await db.flush()

    result = await db.execute(select(Employee).where(Employee.is_active.is_(True)))
    return list(result.scalars().all())


def _pick_employee(ticket: Ticket, employees: list[Employee]) -> Employee | None:
    if not employees:
        return None

    required_skill = ticket.required_skill
    if required_skill:
        for employee in employees:
            if required_skill in employee.skills:
                return employee

    return employees[0]


def _max_workday_minutes(work_start_hour: int, work_end_hour: int) -> int:
    return max(0, (work_end_hour - work_start_hour) * 60)


async def _find_next_slot_start(
    db: AsyncSession,
    employee: Employee,
    duration_minutes: int,
) -> tuple[datetime, datetime]:
    """
    Подбирает ближайший интервал выполнения в рамках рабочего времени сотрудника.

    Слот всегда укладывается в [work_start_hour, work_end_hour] одного календарного дня.
    Если в текущий день времени не хватает, переносит на следующий рабочий день.
    """
    work_start_hour = employee.work_start_hour
    work_end_hour = employee.work_end_hour
    max_daily_minutes = _max_workday_minutes(work_start_hour, work_end_hour)
    if max_daily_minutes <= 0:
        raise ValueError(
            f"Invalid work hours for employee_id={employee.id}: "
            f"{work_start_hour}-{work_end_hour}"
        )

    effective_duration = min(duration_minutes, max_daily_minutes)
    now = now_local()
    current_day = local_today()

    for day_offset in range(MAX_SCHEDULE_LOOKAHEAD_DAYS):
        day = current_day + timedelta(days=day_offset)
        day_start, day_end = workday_bounds(day, work_start_hour, work_end_hour)

        if day_offset == 0:
            candidate = max(now + timedelta(minutes=SCHEDULE_BUFFER_MINUTES), day_start)
        else:
            candidate = day_start

        if candidate >= day_end:
            continue

        result = await db.execute(
            select(Schedule)
            .where(
                Schedule.employee_id == employee.id,
                Schedule.start_time >= day_start,
                Schedule.start_time < day_end,
            )
            .order_by(Schedule.end_time.desc())
        )
        last_slot = result.scalars().first()
        if last_slot and last_slot.end_time > candidate:
            candidate = last_slot.end_time

        if candidate >= day_end:
            continue

        end_time = candidate + timedelta(minutes=effective_duration)
        if end_time <= day_end:
            if effective_duration < duration_minutes:
                logger.warning(
                    "Ticket duration %s min exceeds employee_id=%s workday (%s min); "
                    "scheduled within single workday.",
                    duration_minutes,
                    employee.id,
                    max_daily_minutes,
                )
            return candidate, end_time

    raise RuntimeError(
        f"Could not find schedule slot for employee_id={employee.id} "
        f"within {MAX_SCHEDULE_LOOKAHEAD_DAYS} days"
    )


async def get_existing_schedule_for_ticket(db: AsyncSession, ticket_id: int) -> Schedule | None:
    result = await db.execute(select(Schedule).where(Schedule.ticket_id == ticket_id))
    return result.scalar_one_or_none()


async def schedule_ticket(db: AsyncSession, ticket: Ticket) -> tuple[Schedule, Approval] | None:
    """
    Создаёт предложение по расписанию и запись на утверждение начальнику.

  60/25/15 пока упрощённо: тип слота зависит от приоритета заявки.
    """
    existing_schedule = await get_existing_schedule_for_ticket(db, ticket.id)
    if existing_schedule is not None:
        approval_result = await db.execute(
            select(Approval).where(Approval.proposed_schedule_id == existing_schedule.id)
        )
        approval = approval_result.scalar_one_or_none()
        if approval is not None:
            return existing_schedule, approval

    employees = await ensure_default_employees(db)
    employee = _pick_employee(ticket, employees)
    if employee is None:
        logger.error("No active employees available for ticket_id=%s", ticket.id)
        return None

    duration = ticket.estimated_minutes or 60
    try:
        if ticket.ticket_type == "event_support" and ticket.event_datetime:
            start_time, end_time = event_slot_bounds(ticket.event_datetime)
            ticket.estimated_minutes = EVENT_TOTAL_MINUTES
        else:
            start_time, end_time = await _find_next_slot_start(db, employee, duration)
    except (ValueError, RuntimeError) as exc:
        logger.error(
            "Failed to schedule ticket_id=%s for employee_id=%s: %s",
            ticket.id,
            employee.id,
            exc,
        )
        return None

    schedule = Schedule(
        ticket_id=ticket.id,
        employee_id=employee.id,
        start_time=start_time,
        end_time=end_time,
        slot_type=slot_type_for_priority(ticket.priority),
    )
    db.add(schedule)
    await db.flush()

    approval = Approval(
        proposed_schedule_id=schedule.id,
        status="pending",
    )
    db.add(approval)

    ticket.status = "scheduled"
    logger.info(
        "Scheduled ticket_id=%s to employee_id=%s at %s",
        ticket.id,
        employee.id,
        start_time.isoformat(),
    )
    return schedule, approval


def build_schedule_proposal() -> dict:
    """Заглушка распределения 60/25/15 для будущего расширения."""
    return {"normal": 60, "priority": 25, "reserve": 15}
