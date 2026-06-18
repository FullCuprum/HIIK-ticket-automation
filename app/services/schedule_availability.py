from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.schedule_executor import ScheduleExecutor
from app.models.ticket import Ticket
from app.services.event_support import EVENT_TOTAL_MINUTES, event_slot_bounds
from app.services.schedule_assignment import (
    AssignmentPlan,
    employees_matching_skill,
    pool_capacity_minutes,
    resolve_executor_requirements,
    score_assignment,
    slot_type_for_priority,
    workday_minutes,
    max_schedulable_minutes,
)
from app.utils.datetime_utils import local_day_range, local_today, now_local, workday_bounds

ACTIVE_APPROVAL_STATUSES = ("pending", "approved")
SCHEDULE_BUFFER_MINUTES = 15
MAX_SCHEDULE_LOOKAHEAD_DAYS = 366

EVENT_MANUAL_REVIEW_COMMENT = (
    "Автоназначение: у выбранного исполнителя есть пересечение с другими задачами "
    "в время мероприятия. Требуется проверка администратора."
)


@dataclass
class _SlotCandidate:
    employee_ids: list[int]
    start_time: datetime
    end_time: datetime
    slot_type: str
    score: float
    manual_review: bool = False


async def get_busy_intervals(
    db: AsyncSession,
    employee_id: int,
    range_start: datetime,
    range_end: datetime,
) -> list[tuple[datetime, datetime]]:
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


async def get_pool_minutes_used(
    db: AsyncSession,
    employee_id: int,
    day: date,
    slot_type: str,
) -> int:
    day_start, day_end = local_day_range(day)
    result = await db.execute(
        select(Schedule.start_time, Schedule.end_time)
        .join(ScheduleExecutor, ScheduleExecutor.schedule_id == Schedule.id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            ScheduleExecutor.employee_id == employee_id,
            Schedule.slot_type == slot_type,
            Schedule.start_time >= day_start,
            Schedule.start_time < day_end,
            Approval.status.in_(ACTIVE_APPROVAL_STATUSES),
        )
    )
    total = 0
    for start_time, end_time in result.all():
        total += int((end_time - start_time).total_seconds() // 60)
    return total


async def get_day_buildings(
    db: AsyncSession,
    employee_id: int,
    day: date,
) -> set[str]:
    day_start, day_end = local_day_range(day)
    result = await db.execute(
        select(Ticket.extracted_building)
        .join(Schedule, Schedule.ticket_id == Ticket.id)
        .join(ScheduleExecutor, ScheduleExecutor.schedule_id == Schedule.id)
        .join(Approval, Approval.proposed_schedule_id == Schedule.id)
        .where(
            ScheduleExecutor.employee_id == employee_id,
            Schedule.start_time >= day_start,
            Schedule.start_time < day_end,
            Approval.status.in_(ACTIVE_APPROVAL_STATUSES),
            Ticket.extracted_building.is_not(None),
        )
    )
    return {row[0] for row in result.all() if row[0]}


def week_bounds(reference_day: date) -> tuple[datetime, datetime]:
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
    if probe_end <= probe_start:
        return 0

    time_points = {probe_start, probe_end}
    for start, end in intervals:
        if start < probe_end and end > probe_start:
            time_points.add(max(start, probe_start))
            time_points.add(min(end, probe_end))

    max_count = 0
    for point in sorted(time_points):
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


def _pool_overflow_minutes(
    employee: Employee,
    pool_used: int,
    duration: int,
    slot_type: str,
) -> int:
    capacity = pool_capacity_minutes(employee, slot_type)
    return max(0, pool_used + duration - capacity)


def _workday_overflow_minutes(
    employee: Employee,
    day_minutes: int,
    duration: int,
) -> int:
    return max(0, day_minutes + duration - max_schedulable_minutes(employee))


async def _score_slot(
    db: AsyncSession,
    employee: Employee,
    start_time: datetime,
    end_time: datetime,
    slot_type: str,
    building: str | None,
    *,
    manual_review: bool = False,
) -> float:
    day = start_time.date()
    day_start, _ = workday_bounds(day, employee.work_start_hour, employee.work_end_hour)
    day_minutes, week_minutes, _ = await get_employee_workload(db, employee.id, reference_day=day)
    pool_used = await get_pool_minutes_used(db, employee.id, day, slot_type)
    duration = int((end_time - start_time).total_seconds() // 60)
    day_buildings = await get_day_buildings(db, employee.id, day)

    return score_assignment(
        week_minutes=week_minutes,
        day_minutes=day_minutes,
        start_minutes_from_day_start=(start_time - day_start).total_seconds() / 60,
        same_building=bool(building and building in day_buildings),
        pool_overflow_minutes=_pool_overflow_minutes(employee, pool_used, duration, slot_type),
        workday_overflow_minutes=_workday_overflow_minutes(employee, day_minutes, duration),
        manual_review=manual_review,
    )


async def _pool_allows_slot(
    db: AsyncSession,
    employee: Employee,
    start_time: datetime,
    end_time: datetime,
    slot_type: str,
) -> bool:
    day = start_time.date()
    duration = int((end_time - start_time).total_seconds() // 60)
    pool_used = await get_pool_minutes_used(db, employee.id, day, slot_type)
    day_minutes, _, _ = await get_employee_workload(db, employee.id, reference_day=day)

    if pool_used + duration > pool_capacity_minutes(employee, slot_type):
        return False
    if day_minutes + duration > max_schedulable_minutes(employee):
        return False
    return True


async def iter_viable_slots(
    db: AsyncSession,
    employee: Employee,
    duration_minutes: int,
    slot_type: str,
    *,
    earliest_start: datetime | None = None,
    max_lookahead_days: int = MAX_SCHEDULE_LOOKAHEAD_DAYS,
    stop_after_first_day: bool = True,
) -> list[tuple[datetime, datetime]]:
    max_daily = workday_minutes(employee)
    if max_daily <= 0:
        return []

    effective_duration = min(duration_minutes, max_daily)
    now = now_local()
    current_day = local_today()
    min_start = earliest_start or (now + timedelta(minutes=SCHEDULE_BUFFER_MINUTES))
    slots: list[tuple[datetime, datetime]] = []

    for day_offset in range(max_lookahead_days):
        day = current_day + timedelta(days=day_offset)
        day_start, day_end = workday_bounds(day, employee.work_start_hour, employee.work_end_hour)
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

            if not interval_is_available(
                busy,
                candidate_start,
                candidate_end,
                employee.max_parallel_tasks,
            ):
                continue

            if not await _pool_allows_slot(db, employee, candidate_start, candidate_end, slot_type):
                continue

            slots.append((candidate_start, candidate_end))

        if stop_after_first_day and slots:
            break

    return slots


async def find_first_free_slot(
    db: AsyncSession,
    employee: Employee,
    duration_minutes: int,
    *,
    earliest_start: datetime | None = None,
    slot_type: str = "normal",
    max_lookahead_days: int = MAX_SCHEDULE_LOOKAHEAD_DAYS,
) -> tuple[datetime, datetime]:
    slots = await iter_viable_slots(
        db,
        employee,
        duration_minutes,
        slot_type,
        earliest_start=earliest_start,
        max_lookahead_days=max_lookahead_days,
    )
    if not slots:
        raise RuntimeError(
            f"Could not find schedule slot for employee_id={employee.id} "
            f"within {max_lookahead_days} days"
        )
    return slots[0]


def employees_with_skill(employees: list[Employee], required_skill: str | None) -> list[Employee]:
    if not required_skill:
        return list(employees)
    matched = [employee for employee in employees if required_skill in employee.skills]
    return matched or list(employees)


async def _pick_secondary_executor(
    db: AsyncSession,
    employees: list[Employee],
    requirement,
    start_time: datetime,
    end_time: datetime,
    exclude_ids: set[int],
    building: str | None,
    slot_type: str,
) -> tuple[Employee | None, bool]:
    candidates = employees_matching_skill(employees, requirement.skill, exclude_ids=exclude_ids)
    if not candidates:
        return None, True

    ranked: list[tuple[float, Employee, bool]] = []
    for employee in candidates:
        busy = await get_busy_intervals(db, employee.id, start_time, end_time)
        available = interval_is_available(
            busy,
            start_time,
            end_time,
            employee.max_parallel_tasks,
        )
        pool_ok = await _pool_allows_slot(db, employee, start_time, end_time, slot_type)
        manual = not (available and pool_ok)
        score = await _score_slot(
            db,
            employee,
            start_time,
            end_time,
            slot_type,
            building,
            manual_review=manual,
        )
        ranked.append((score, employee, manual))

    ranked.sort(key=lambda item: item[0])
    _best_score, best_employee, manual = ranked[0]
    return best_employee, manual


async def _plan_flexible_assignment(
    db: AsyncSession,
    ticket: Ticket,
    employees: list[Employee],
) -> AssignmentPlan | None:
    requirements = resolve_executor_requirements(ticket)
    slot_type = slot_type_for_priority(ticket.priority)
    duration = ticket.estimated_minutes or 60
    building = ticket.extracted_building

    primary_candidates = employees_matching_skill(employees, requirements[0].skill)
    best: _SlotCandidate | None = None

    for primary in primary_candidates:
        slots = await iter_viable_slots(
            db,
            primary,
            duration,
            slot_type,
            stop_after_first_day=False,
            max_lookahead_days=14,
        )
        for start_time, end_time in slots:
            team_ids = [primary.id]
            manual_review = False

            if len(requirements) > 1:
                secondary, secondary_manual = await _pick_secondary_executor(
                    db,
                    employees,
                    requirements[1],
                    start_time,
                    end_time,
                    exclude_ids={primary.id},
                    building=building,
                    slot_type=slot_type,
                )
                if secondary is None:
                    continue
                team_ids.append(secondary.id)
                manual_review = manual_review or secondary_manual

            score = await _score_slot(
                db,
                primary,
                start_time,
                end_time,
                slot_type,
                building,
                manual_review=manual_review,
            )

            if best is None or score < best.score:
                best = _SlotCandidate(
                    employee_ids=team_ids,
                    start_time=start_time,
                    end_time=end_time,
                    slot_type=slot_type,
                    score=score,
                    manual_review=manual_review,
                )

    if best is None:
        return None

    comment = None
    if best.manual_review:
        comment = (
            "Автоназначение: для части исполнителей есть пересечения или превышение пула. "
            "Требуется проверка администратора."
        )

    return AssignmentPlan(
        employee_ids=best.employee_ids,
        start_time=best.start_time,
        end_time=best.end_time,
        slot_type=best.slot_type,
        manual_review_comment=comment,
        score=best.score,
    )


async def _plan_event_assignment(
    db: AsyncSession,
    ticket: Ticket,
    employees: list[Employee],
) -> AssignmentPlan | None:
    if not ticket.event_datetime:
        return None

    start_time, end_time = event_slot_bounds(ticket.event_datetime)
    ticket.estimated_minutes = EVENT_TOTAL_MINUTES
    requirements = resolve_executor_requirements(ticket)
    slot_type = "high_priority"
    building = ticket.extracted_building

    team_ids: list[int] = []
    manual_review = False
    exclude: set[int] = set()
    total_score = 0.0

    for requirement in requirements:
        candidates = employees_matching_skill(employees, requirement.skill, exclude_ids=exclude)
        if not candidates:
            return None

        ranked: list[tuple[float, Employee, bool]] = []
        for employee in candidates:
            busy = await get_busy_intervals(db, employee.id, start_time, end_time)
            available = interval_is_available(
                busy,
                start_time,
                end_time,
                employee.max_parallel_tasks,
            )
            pool_ok = await _pool_allows_slot(db, employee, start_time, end_time, slot_type)
            manual = not (available and pool_ok)
            score = await _score_slot(
                db,
                employee,
                start_time,
                end_time,
                slot_type,
                building,
                manual_review=manual,
            )
            ranked.append((score, employee, manual))

        ranked.sort(key=lambda item: item[0])
        score, employee, manual = ranked[0]
        team_ids.append(employee.id)
        exclude.add(employee.id)
        total_score += score
        manual_review = manual_review or manual

    comment = EVENT_MANUAL_REVIEW_COMMENT if manual_review else None
    return AssignmentPlan(
        employee_ids=team_ids,
        start_time=start_time,
        end_time=end_time,
        slot_type=slot_type,
        manual_review_comment=comment,
        score=total_score,
    )


async def plan_ticket_assignment(
    db: AsyncSession,
    ticket: Ticket,
    employees: list[Employee],
) -> AssignmentPlan | None:
    if ticket.ticket_type == "event_support" and ticket.event_datetime:
        return await _plan_event_assignment(db, ticket, employees)
    return await _plan_flexible_assignment(db, ticket, employees)


async def pick_employee_by_workload(
    db: AsyncSession,
    employees: list[Employee],
    required_skill: str | None,
    *,
    reference_day: date | None = None,
) -> Employee | None:
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
    candidates = employees_matching_skill(employees, required_skill)
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
