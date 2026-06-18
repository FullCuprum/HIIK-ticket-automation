from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.ticket import Ticket
from app.services.schedule_assignment import slot_type_for_priority
from app.services.schedule_availability import plan_ticket_assignment
from app.services.schedule_executors import set_schedule_executors

logger = logging.getLogger(__name__)

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
    Создаёт предложение по расписанию с учётом:
    - автоназначения нескольких исполнителей по типу заявки;
    - пулов 60/25/15;
    - скоринга (навык, загрузка, здание, время, переработка).
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

    try:
        plan = await plan_ticket_assignment(db, ticket, employees)
    except (ValueError, RuntimeError) as exc:
        logger.error("Failed to schedule ticket_id=%s: %s", ticket.id, exc)
        return None

    if plan is None:
        logger.error("No assignment plan for ticket_id=%s", ticket.id)
        return None

    primary_employee_id = plan.employee_ids[0]
    schedule = Schedule(
        ticket_id=ticket.id,
        employee_id=primary_employee_id,
        start_time=plan.start_time,
        end_time=plan.end_time,
        slot_type=plan.slot_type or slot_type_for_priority(ticket.priority),
    )
    db.add(schedule)
    await db.flush()

    employee_map = {employee.id: employee for employee in employees}
    primary = employee_map.get(primary_employee_id)
    if primary is None:
        logger.error("Primary employee_id=%s not found for ticket_id=%s", primary_employee_id, ticket.id)
        return None

    await set_schedule_executors(db, schedule, plan.employee_ids)

    approval = Approval(
        proposed_schedule_id=schedule.id,
        status="pending",
        manager_comment=plan.manual_review_comment,
    )
    db.add(approval)

    ticket.status = "scheduled"
    logger.info(
        "Scheduled ticket_id=%s executors=%s at %s score=%.2f manual_review=%s",
        ticket.id,
        plan.employee_ids,
        plan.start_time.isoformat(),
        plan.score,
        bool(plan.manual_review_comment),
    )
    return schedule, approval
