from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.schedule_executor import ScheduleExecutor
from app.utils.datetime_utils import local_day_range, local_today, now_local, workday_bounds

ACTIVE_APPROVAL_STATUSES = ("pending", "approved")


async def get_busy_intervals(
    db: AsyncSession,
    employee_id: int,
    range_start: datetime,
    range_end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Возвращает занятые интервалы сотрудника через schedule_executors."""
    result = await db.execute(
        select(Schedule.start_time, Schedule.end_time)
        .join(ScheduleExecutor, ScheduleExecutor.schedule_id == Schedule.id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            ScheduleExecutor.employee_id == employee_id,
            Schedule.start_time < range_end,
            Schedule.end_time > range_start,
            Approval.status.in_(ACTIVE_APPROVAL_STATUSES),
        )
        .order_by(Schedule.start_time)
    )
    return [(row[0], row[1]) for row in result.all()]


async def get_scheduled_minutes(
    db: AsyncSession,
    employee_id: int,
    range_start: datetime,
    range_end: datetime,
) -> tuple[int, int]:
    """Сумма минут и число слотов в интервале [range_start, range_end)."""
    result = await db.execute(
        select(Schedule.start_time, Schedule.end_time)
        .join(ScheduleExecutor, ScheduleExecutor.schedule_id == Schedule.id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            ScheduleExecutor.employee_id == employee_id,
            Schedule.start_time < range_end,
            Schedule.end_time > range_start,
            Approval.status.in_(ACTIVE_APPROVAL_STATUSES),
        )
    )

    total_minutes = 0
    tasks_count = 0
    for start_time, end_time in result.all():
        overlap_start = max(start_time, range_start)
        overlap_end = min(end_time, range_end)
        if overlap_end > overlap_start:
            total_minutes += int((overlap_end - overlap_start).total_seconds() // 60)
            tasks_count += 1
    return total_minutes, tasks_count


def week_bounds(reference_day: date) -> tuple[datetime, datetime]:
    """Календарная неделя (пн–вс) для reference_day."""
    monday = reference_day - timedelta(days=reference_day.weekday())
    week_start, _ = local_day_range(monday)
    week_end_day = monday + timedelta(days=7)
    _, week_end = local_day_range(week_end_day)
    return week_start, week_end


async def get_employee_workload(
    db: AsyncSession,
    employee_id: int,
    *,
    reference_day: date | None = None,
) -> tuple[int, int, int]:
    """Возвращает (минуты_сегодня, минуты_неделя, задач_сегодня)."""
    day = reference_day or local_today()
    day_start, day_end = local_day_range(day)
    week_start, week_end = week_bounds(day)

    day_minutes, tasks_today = await get_scheduled_minutes(db, employee_id, day_start, day_end)
    week_minutes, _ = await get_scheduled_minutes(db, employee_id, week_start, week_end)
    return day_minutes, week_minutes, tasks_today


def peak_concurrency(
    intervals: list[tuple[datetime, datetime]],
    probe_start: datetime,
    probe_end: datetime,
) -> int:
    """Максимальное число одновременных задач в [probe_start, probe_end)."""
    if probe_end <= probe_start:
        return 0

    time_points = {probe_start, probe_end}
    for start, end in intervals:
        if start < probe_end and end > probe_start:
            time_points.add(max(start, probe_start))
            time_points.add(min(end, probe_end))

    sorted_points = sorted(time_points)
    max_count = 0
    for point in sorted_points:
        if point < probe_start or point >= probe_end:
            continue
        count = sum(1 for start, end in intervals if start <= point < end)
        max_count = max(max_count, count)
    return max_count


def interval_is_available(
    intervals: list[tuple[datetime, datetime]],
    probe_start: datetime,
    probe_end: datetime,
    max_parallel_tasks: int,
) -> bool:
    return peak_concurrency(intervals, probe_start, probe_end) < max_parallel_tasks


def _max_workday_minutes(work_start_hour: int, work_end_hour: int) -> int:
    return max(0, (work_end_hour - work_start_hour) * 60)


async def find_first_free_slot(
    db: AsyncSession,
    employee: Employee,
    duration_minutes: int,
    *,
    earliest_start: datetime | None = None,
    max_lookahead_days: int = 366,
) -> tuple[datetime, datetime]:
    """
    Ищет первый свободный интервал длительностью duration_minutes
    с учётом max_parallel_tasks и schedule_executors.
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
    min_start = earliest_start or (now + timedelta(minutes=15))

    for day_offset in range(max_lookahead_days):
        day = current_day + timedelta(days=day_offset)
        day_start, day_end = workday_bounds(day, work_start_hour, work_end_hour)
        busy = await get_busy_intervals(db, employee.id, day_start, day_end)

        candidate_starts = {day_start}
        for _start, end in busy:
            if day_start <= end < day_end:
                candidate_starts.add(end)

        for candidate_start in sorted(candidate_starts):
            if candidate_start < min_start:
                candidate_start = max(candidate_start, min_start)
            if candidate_start >= day_end:
                continue

            candidate_end = candidate_start + timedelta(minutes=effective_duration)
            if candidate_end > day_end:
                continue

            if interval_is_available(
                busy,
                candidate_start,
                candidate_end,
                employee.max_parallel_tasks,
            ):
                return candidate_start, candidate_end

    raise RuntimeError(
        f"Could not find schedule slot for employee_id={employee.id} "
        f"within {max_lookahead_days} days"
    )


def employees_with_skill(employees: list[Employee], required_skill: str | None) -> list[Employee]:
    if not required_skill:
        return list(employees)
    matched = [employee for employee in employees if required_skill in employee.skills]
    return matched or list(employees)


async def pick_employee_by_workload(
    db: AsyncSession,
    employees: list[Employee],
    required_skill: str | None,
    *,
    reference_day: date | None = None,
) -> Employee | None:
    """Выбирает исполнителя с нужным навыком и наименьшей загрузкой."""
    candidates = employees_with_skill(employees, required_skill)
    if not candidates:
        return None

    best_employee: Employee | None = None
    best_key: tuple[int, int, int] | None = None
    for employee in candidates:
        day_minutes, week_minutes, _tasks = await get_employee_workload(
            db,
            employee.id,
            reference_day=reference_day,
        )
        key = (week_minutes, day_minutes, employee.id)
        if best_key is None or key < best_key:
            best_key = key
            best_employee = employee
    return best_employee


async def pick_employee_for_fixed_interval(
    db: AsyncSession,
    employees: list[Employee],
    required_skill: str,
    start_time: datetime,
    end_time: datetime,
) -> tuple[Employee | None, bool]:
    """
    Подбирает исполнителя для фиксированного интервала (мероприятия).

    Возвращает (employee, needs_manual_review).
    needs_manual_review=True, если свободных нет и выбран наименее загруженный.
    """
    candidates = employees_with_skill(employees, required_skill)
    if not candidates:
        candidates = list(employees)
    if not candidates:
        return None, True

    ranked: list[tuple[tuple[int, int, int], Employee]] = []
    reference_day = start_time.date()
    for employee in candidates:
        day_minutes, week_minutes, _tasks = await get_employee_workload(
            db,
            employee.id,
            reference_day=reference_day,
        )
        ranked.append(((week_minutes, day_minutes, employee.id), employee))

    ranked.sort(key=lambda item: item[0])

    for _key, employee in ranked:
        busy = await get_busy_intervals(db, employee.id, start_time, end_time)
        if interval_is_available(
            busy,
            start_time,
            end_time,
            employee.max_parallel_tasks,
        ):
            return employee, False

    return ranked[0][1], True
