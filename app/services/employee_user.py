from __future__ import annotations

import secrets
import string
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.user import User
from app.utils.datetime_utils import now_local
from app.utils.password import hash_password
from app.utils.username import generate_unique_username

DEFAULT_EMPLOYEE_PASSWORD_LENGTH = 10


def generate_temp_password(length: int = DEFAULT_EMPLOYEE_PASSWORD_LENGTH) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


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
    now = now_local()
    result = await db.execute(
        select(Schedule.id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            Schedule.employee_id == employee_id,
            Approval.status.in_(["pending", "approved"]),
            Schedule.end_time > now,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def employee_has_recent_completed_tasks(db: AsyncSession, employee_id: int) -> bool:
    now = now_local()
    since = now - timedelta(days=30)
    result = await db.execute(
        select(Schedule.id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            Schedule.employee_id == employee_id,
            Approval.status == "approved",
            Schedule.end_time <= now,
            Schedule.end_time >= since,
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
