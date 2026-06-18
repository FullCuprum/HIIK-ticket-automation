from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.schedule_availability import (
    interval_is_available,
    peak_concurrency,
)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 18, hour, minute, tzinfo=ZoneInfo("Asia/Vladivostok"))


def test_peak_concurrency_no_overlap():
    intervals = [(_dt(10), _dt(11))]
    assert peak_concurrency(intervals, _dt(12), _dt(13)) == 0


def test_peak_concurrency_single_overlap():
    intervals = [(_dt(10), _dt(12))]
    assert peak_concurrency(intervals, _dt(11), _dt(13)) == 1


def test_peak_concurrency_parallel_tasks():
    intervals = [
        (_dt(10), _dt(12)),
        (_dt(10, 30), _dt(12, 30)),
    ]
    assert peak_concurrency(intervals, _dt(11), _dt(11, 30)) == 2


def test_interval_is_available_respects_max_parallel():
    intervals = [
        (_dt(10), _dt(12)),
        (_dt(10, 30), _dt(12, 30)),
    ]
    assert interval_is_available(intervals, _dt(11), _dt(11, 30), max_parallel_tasks=2) is False
    assert interval_is_available(intervals, _dt(11), _dt(11, 30), max_parallel_tasks=3) is True


def test_interval_is_available_fits_in_gap():
    intervals = [(_dt(9), _dt(10)), (_dt(11), _dt(12))]
    assert interval_is_available(intervals, _dt(10), _dt(10, 45), max_parallel_tasks=1) is True
    assert interval_is_available(intervals, _dt(10, 30), _dt(11, 15), max_parallel_tasks=1) is False
