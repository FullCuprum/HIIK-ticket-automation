from __future__ import annotations

from datetime import datetime, timedelta

from app.utils.datetime_utils import get_app_timezone

EVENT_PREP_MINUTES = 30
EVENT_ACTIVE_MINUTES = 90
EVENT_TOTAL_MINUTES = EVENT_PREP_MINUTES + EVENT_ACTIVE_MINUTES


def apply_event_support_defaults(data: dict) -> dict:
    if data.get("ticket_type") == "event_support":
        data["priority"] = "high"
        data["estimated_minutes"] = EVENT_TOTAL_MINUTES
    return data


def event_slot_bounds(event_datetime: datetime) -> tuple[datetime, datetime]:
    tz = get_app_timezone()
    if event_datetime.tzinfo is None:
        event_dt = event_datetime.replace(tzinfo=tz)
    else:
        event_dt = event_datetime.astimezone(tz)

    start_time = event_dt - timedelta(minutes=EVENT_PREP_MINUTES)
    end_time = event_dt + timedelta(minutes=EVENT_ACTIVE_MINUTES)
    return start_time, end_time
