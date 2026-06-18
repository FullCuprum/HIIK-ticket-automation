from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.parser import get_ticket_parser

CASES_PATH = Path(__file__).parent / "data" / "complex_examples.json"


def load_cases() -> list[dict]:
    with CASES_PATH.open(encoding="utf-8") as file:
        return json.load(file)


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: f"complex-{case['id']}")
def test_complex_example(case: dict) -> None:
    parsed = get_ticket_parser().parse(case["text"])
    expected = case["expected"]

    for field, value in expected.items():
        assert parsed.get(field) == value, (
            f"case {case['id']}: field {field}: expected {value!r}, got {parsed.get(field)!r}"
        )

    for field in case.get("missing_fields", []):
        assert field in parsed["missing_fields"]

    for field in case.get("not_missing_fields", []):
        assert field not in parsed["missing_fields"]
