from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.schedule_executor import ScheduleExecutor
from app.models.ticket import Ticket
from app.services.event_support import EVENT_TOTAL_MINUTES, event_slot_bounds
from app.services.schedule_availability import (
    find_first_free_slot,
    pick_employee_by_workload,
    pick_employee_for_fixed_interval,
)

logger = logging.getLogger(__name__)

EVENT_MANUAL_REVIEW_COMMENT = (
    "Автоназначение: у выбранного исполнителя есть пересечение с другими задачами "
    "в время мероприятия. Требуется проверка администратора."
)

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


async def get_existing_schedule_for_ticket(db: AsyncSession, ticket_id: int) -> Schedule | None:
    result = await db.execute(select(Schedule).where(Schedule.ticket_id == ticket_id))
    return result.scalar_one_or_none()


async def schedule_ticket(db: AsyncSession, ticket: Ticket) -> tuple[Schedule, Approval] | None:
    """
    Создаёт предложение по расписанию и запись на утверждение начальнику.

    Исполнитель выбирается по навыку и загрузке; время — первый свободный интервал
    с учётом max_parallel_tasks и всех назначений через schedule_executors.
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
    if not employees:
        logger.error("No active employees available for ticket_id=%s", ticket.id)
        return None

    duration = ticket.estimated_minutes or 60
    manual_review_comment: str | None = None

    try:
        if ticket.ticket_type == "event_support" and ticket.event_datetime:
            start_time, end_time = event_slot_bounds(ticket.event_datetime)
            ticket.estimated_minutes = EVENT_TOTAL_MINUTES
            employee, needs_manual_review = await pick_employee_for_fixed_interval(
                db,
                employees,
                "event_support",
                start_time,
                end_time,
            )
            if employee is None:
                logger.error("No executor available for event ticket_id=%s", ticket.id)
                return None
            if needs_manual_review:
                manual_review_comment = EVENT_MANUAL_REVIEW_COMMENT
                logger.warning(
                    "Event ticket_id=%s assigned to busy employee_id=%s; manual review required",
                    ticket.id,
                    employee.id,
                )
        else:
            employee = await pick_employee_by_workload(
                db,
                employees,
                ticket.required_skill,
            )
            if employee is None:
                logger.error("No executor available for ticket_id=%s", ticket.id)
                return None
            start_time, end_time = await find_first_free_slot(db, employee, duration)
    except (ValueError, RuntimeError) as exc:
        logger.error(
            "Failed to schedule ticket_id=%s: %s",
            ticket.id,
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
    db.add(ScheduleExecutor(schedule_id=schedule.id, employee_id=employee.id))

    approval = Approval(
        proposed_schedule_id=schedule.id,
        status="pending",
        manager_comment=manual_review_comment,
    )
    db.add(approval)

    ticket.status = "scheduled"
    logger.info(
        "Scheduled ticket_id=%s to employee_id=%s at %s (manual_review=%s)",
        ticket.id,
        employee.id,
        start_time.isoformat(),
        bool(manual_review_comment),
    )
    return schedule, approval


def build_schedule_proposal() -> dict:
    """Заглушка распределения 60/25/15 для будущего расширения."""
    return {"normal": 60, "priority": 25, "reserve": 15}
