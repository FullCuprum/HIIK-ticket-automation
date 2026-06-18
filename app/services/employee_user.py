from __future__ import annotations

import secrets
import string
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.schedule_executor import ScheduleExecutor
from app.models.ticket import Ticket
from app.models.user import User
from app.utils.datetime_utils import now_local
from app.utils.password import hash_password
from app.utils.username import generate_unique_username

DEFAULT_EMPLOYEE_PASSWORD_LENGTH = 10


def generate_temp_password(length: int = DEFAULT_EMPLOYEE_PASSWORD_LENGTH) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def get_employee_id_for_username(db: AsyncSession, username: str) -> int | None:
    result = await db.execute(
        select(Employee.id)
        .join(User, Employee.user_id == User.id)
        .where(User.username == username.strip())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_user_for_employee(
    db: AsyncSession,
    *,
    full_name: str,
    is_active: bool,
) -> tuple[User, str]:
    username = await generate_unique_username(db, full_name)
    password = generate_temp_password()
    user = User(
        username=username,
        password_hash=hash_password(password),
        role="employee",
        full_name=full_name.strip(),
        must_change_password=True,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    return user, password


async def sync_linked_user(
    db: AsyncSession,
    employee: Employee,
    *,
    full_name: str | None = None,
    is_active: bool | None = None,
) -> None:
    if employee.user_id is None:
        return

    user = await db.get(User, employee.user_id)
    if user is None:
        return

    if full_name is not None:
        user.full_name = full_name.strip()
    if is_active is not None:
        user.is_active = is_active


async def employee_has_scheduled_tasks(db: AsyncSession, employee_id: int) -> bool:
    result = await db.execute(
        select(Schedule.id)
        .join(ScheduleExecutor, ScheduleExecutor.schedule_id == Schedule.id)
        .join(Ticket, Ticket.id == Schedule.ticket_id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            ScheduleExecutor.employee_id == employee_id,
            Approval.status == "approved",
            Ticket.status == "approved",
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def employee_has_recent_completed_tasks(db: AsyncSession, employee_id: int) -> bool:
    since = now_local() - timedelta(days=30)
    result = await db.execute(
        select(Ticket.id)
        .join(Schedule, Schedule.ticket_id == Ticket.id)
        .join(ScheduleExecutor, ScheduleExecutor.schedule_id == Schedule.id)
        .where(
            ScheduleExecutor.employee_id == employee_id,
            Ticket.status == "completed",
            Ticket.completed_at.is_not(None),
            Ticket.completed_at >= since,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def ensure_users_for_employees_without_account(db: AsyncSession) -> None:
    result = await db.execute(select(Employee).where(Employee.user_id.is_(None)))
    employees = list(result.scalars().all())
    for employee in employees:
        user, _password = await create_user_for_employee(
            db,
            full_name=employee.full_name,
            is_active=employee.is_active,
        )
        employee.user_id = user.id
