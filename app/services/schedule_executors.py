from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.schedule_executor import ScheduleExecutor


async def get_schedule_executor_ids(db: AsyncSession, schedule_id: int) -> list[int]:
    result = await db.execute(
        select(ScheduleExecutor.employee_id)
        .where(ScheduleExecutor.schedule_id == schedule_id)
        .order_by(ScheduleExecutor.id)
    )
    return [row[0] for row in result.all()]


async def load_schedule_executor_info(
    db: AsyncSession,
    schedule: Schedule,
) -> tuple[list[int], list[str], str]:
    result = await db.execute(
        select(Employee.id, Employee.full_name)
        .join(ScheduleExecutor, ScheduleExecutor.employee_id == Employee.id)
        .where(ScheduleExecutor.schedule_id == schedule.id)
        .order_by(ScheduleExecutor.id)
    )
    rows = result.all()
    if not rows:
        employee = await db.get(Employee, schedule.employee_id)
        if employee is None:
            return [], [], "—"
        return [employee.id], [employee.full_name], employee.full_name

    employee_ids = [row[0] for row in rows]
    employee_names = [row[1] for row in rows]
    return employee_ids, employee_names, ", ".join(employee_names)


async def set_schedule_executors(
    db: AsyncSession,
    schedule: Schedule,
    employee_ids: list[int],
) -> None:
    unique_ids: list[int] = []
    for employee_id in employee_ids:
        if employee_id not in unique_ids:
            unique_ids.append(employee_id)

    if not unique_ids:
        raise ValueError("At least one executor must be selected")

    await db.execute(
        delete(ScheduleExecutor).where(ScheduleExecutor.schedule_id == schedule.id)
    )
    for employee_id in unique_ids:
        db.add(ScheduleExecutor(schedule_id=schedule.id, employee_id=employee_id))

    schedule.employee_id = unique_ids[0]


async def is_schedule_executor(
    db: AsyncSession,
    schedule_id: int,
    employee_id: int,
) -> bool:
    executor_ids = await get_schedule_executor_ids(db, schedule_id)
    if executor_ids:
        return employee_id in executor_ids

    schedule = await db.get(Schedule, schedule_id)
    return schedule is not None and schedule.employee_id == employee_id
