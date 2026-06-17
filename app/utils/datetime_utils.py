from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.config import get_settings


@lru_cache
def get_app_timezone() -> ZoneInfo:
    """Часовой пояс места использования системы (по умолчанию UTC+10)."""
    return ZoneInfo(get_settings().APP_TIMEZONE)


def now_local() -> datetime:
    return datetime.now(get_app_timezone())


def local_today() -> date:
    return now_local().date()


def workday_bounds(day: date, work_start_hour: int, work_end_hour: int) -> tuple[datetime, datetime]:
    tz = get_app_timezone()
    day_start = datetime.combine(day, time(hour=work_start_hour, minute=0), tzinfo=tz)
    day_end = datetime.combine(day, time(hour=work_end_hour, minute=0), tzinfo=tz)
    return day_start, day_end


def local_day_range(day: date) -> tuple[datetime, datetime]:
    """Границы календарного дня в локальном часовом поясе [start, end)."""
    tz = get_app_timezone()
    start = datetime.combine(day, time(0, 0), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=tz)
    return start, end
