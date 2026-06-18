from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.parser import get_ticket_parser

MANUAL_PATH = Path(__file__).parent / "data" / "manual_ticket_classification.json"


def load_manual_cases() -> list[dict]:
    with MANUAL_PATH.open(encoding="utf-8") as file:
        return json.load(file)


@pytest.mark.parametrize("case", load_manual_cases(), ids=lambda case: f"manual-{case['id']}")
def test_manual_ticket_type_classification(case: dict) -> None:
    parsed = get_ticket_parser().parse(case["text"])
    assert parsed.get("ticket_type") == case["manual_type"], (
        f"case {case['id']}: expected {case['manual_type']!r}, got {parsed.get('ticket_type')!r}"
    )


def test_manual_classification_coverage() -> None:
    cases = load_manual_cases()
    types = {case["manual_type"] for case in cases}
    assert types == {
        "repair",
        "software_installation",
        "event_support",
        "workspace_setup",
        "consultation",
        "video_surveillance",
    }
    assert len(cases) == 30
