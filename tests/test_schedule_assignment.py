from types import SimpleNamespace

from app.models.employee import Employee
from app.services.schedule_assignment import (
    is_mass_repair,
    pool_capacity_minutes,
    resolve_executor_requirements,
    score_assignment,
    slot_type_for_priority,
    workday_minutes,
    build_schedule_proposal,
)


def _employee(**kwargs) -> Employee:
    defaults = {
        "id": 1,
        "full_name": "Test",
        "position": "Test",
        "skills": ["hardware_support"],
        "max_parallel_tasks": 2,
        "is_active": True,
        "work_start_hour": 9,
        "work_end_hour": 18,
        "phone": "",
        "email": "",
        "user_id": None,
    }
    defaults.update(kwargs)
    return Employee(**defaults)


def _ticket(**kwargs):
    defaults = {
        "raw_text": "",
        "ticket_type": "repair",
        "extracted_problem": "",
        "required_skill": "hardware_support",
        "priority": "low",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_build_schedule_proposal_ratios():
    assert build_schedule_proposal() == {"normal": 60, "priority": 25, "reserve": 15}


def test_pool_capacity_minutes():
    employee = _employee(work_start_hour=9, work_end_hour=18)
    assert workday_minutes(employee) == 540
    assert pool_capacity_minutes(employee, "normal") == 324
    assert pool_capacity_minutes(employee, "high_priority") == 135


def test_slot_type_for_priority():
    assert slot_type_for_priority("high") == "high_priority"
    assert slot_type_for_priority("low") == "normal"


def test_mass_repair_detection():
    ticket = _ticket(
        ticket_type="repair",
        raw_text="Перестали работать 5 компьютеров в компьютерном классе",
    )
    assert is_mass_repair(ticket) is True


def test_mass_repair_single_device_false():
    ticket = _ticket(
        ticket_type="repair",
        raw_text="Не работает принтер в кабинете 101",
    )
    assert is_mass_repair(ticket) is False


def test_event_support_requires_two_skills():
    ticket = _ticket(ticket_type="event_support")
    requirements = resolve_executor_requirements(ticket)
    assert len(requirements) == 2
    assert requirements[0].skill == "network_engineer"
    assert requirements[1].skill == "event_support"


def test_mass_repair_requires_two_executors():
    ticket = _ticket(
        ticket_type="repair",
        raw_text="не работают 5 компьютеров",
        required_skill="hardware_support",
    )
    requirements = resolve_executor_requirements(ticket)
    assert len(requirements) == 2


def test_default_single_executor():
    ticket = _ticket(ticket_type="software_installation", required_skill="software_admin")
    requirements = resolve_executor_requirements(ticket)
    assert len(requirements) == 1


def test_score_prefers_same_building():
    base = dict(week_minutes=100, day_minutes=50, start_minutes_from_day_start=120)
    with_building = score_assignment(**base, same_building=True, pool_overflow_minutes=0, workday_overflow_minutes=0, manual_review=False)
    without = score_assignment(**base, same_building=False, pool_overflow_minutes=0, workday_overflow_minutes=0, manual_review=False)
    assert with_building < without


def test_score_penalizes_pool_overflow():
    base = dict(
        week_minutes=100,
        day_minutes=50,
        start_minutes_from_day_start=120,
        same_building=False,
        workday_overflow_minutes=0,
        manual_review=False,
    )
    ok = score_assignment(**base, pool_overflow_minutes=0)
    overflow = score_assignment(**base, pool_overflow_minutes=30)
    assert ok < overflow
