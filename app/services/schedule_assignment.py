from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.models.employee import Employee
from app.models.ticket import Ticket

POOL_NORMAL_RATIO = 0.60
POOL_HIGH_RATIO = 0.25
POOL_RESERVE_RATIO = 0.15

MASS_REPAIR_PATTERNS = (
    re.compile(r"\d+\s+(?:компьютер|пк|рабоч(?:их|ее|ие)\s+мест)", re.IGNORECASE),
    re.compile(r"несколько\s+(?:компьютер|пк|рабоч)", re.IGNORECASE),
    re.compile(r"массов", re.IGNORECASE),
    re.compile(r"компьютерн\w*\s+класс", re.IGNORECASE),
    re.compile(r"все\s+компьютер", re.IGNORECASE),
)


@dataclass(frozen=True)
class ExecutorRequirement:
    skill: str
    label: str = ""


@dataclass
class AssignmentPlan:
    employee_ids: list[int]
    start_time: datetime
    end_time: datetime
    slot_type: str
    manual_review_comment: str | None = None
    score: float = 0.0


def slot_type_for_priority(priority: str) -> str:
    return "high_priority" if priority == "high" else "normal"


def workday_minutes(employee: Employee) -> int:
    return max(0, (employee.work_end_hour - employee.work_start_hour) * 60)


def pool_capacity_minutes(employee: Employee, slot_type: str) -> int:
    total = workday_minutes(employee)
    if slot_type == "high_priority":
        return int(total * POOL_HIGH_RATIO)
    return int(total * POOL_NORMAL_RATIO)


def max_schedulable_minutes(employee: Employee) -> int:
    """Максимум минут, которые можно автоматически планировать (без резерва 15%)."""
    total = workday_minutes(employee)
    return int(total * (POOL_NORMAL_RATIO + POOL_HIGH_RATIO))


def is_mass_repair(ticket: Ticket) -> bool:
    if ticket.ticket_type != "repair":
        return False
    text = f"{ticket.raw_text} {ticket.extracted_problem or ''}".lower()
    return any(pattern.search(text) for pattern in MASS_REPAIR_PATTERNS)


def resolve_executor_requirements(ticket: Ticket) -> list[ExecutorRequirement]:
    if ticket.ticket_type == "event_support":
        return [
            ExecutorRequirement(skill="network_engineer", label="сеть"),
            ExecutorRequirement(skill="event_support", label="мероприятия"),
        ]

    if is_mass_repair(ticket):
        skill = ticket.required_skill or "hardware_support"
        return [
            ExecutorRequirement(skill=skill, label="исполнитель 1"),
            ExecutorRequirement(skill=skill, label="исполнитель 2"),
        ]

    return [ExecutorRequirement(skill=ticket.required_skill or "general_support")]


def employees_matching_skill(
    employees: list[Employee],
    skill: str,
    *,
    exclude_ids: set[int] | None = None,
) -> list[Employee]:
    excluded = exclude_ids or set()
    matched = [
        employee
        for employee in employees
        if employee.id not in excluded and skill in employee.skills
    ]
    if matched:
        return matched
    return [employee for employee in employees if employee.id not in excluded]


def score_assignment(
    *,
    week_minutes: int,
    day_minutes: int,
    start_minutes_from_day_start: float,
    same_building: bool,
    pool_overflow_minutes: int,
    workday_overflow_minutes: int,
    manual_review: bool,
) -> float:
    """Меньше — лучше."""
    score = week_minutes * 0.5 + day_minutes * 0.3 + start_minutes_from_day_start * 0.05
    if same_building:
        score -= 40.0
    score += pool_overflow_minutes * 8.0
    score += workday_overflow_minutes * 12.0
    if manual_review:
        score += 200.0
    return score


def build_schedule_proposal() -> dict[str, int]:
    return {
        "normal": int(POOL_NORMAL_RATIO * 100),
        "priority": int(POOL_HIGH_RATIO * 100),
        "reserve": int(POOL_RESERVE_RATIO * 100),
    }
