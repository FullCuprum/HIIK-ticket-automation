from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.parser import get_ticket_parser

GOLDEN_PATH = Path(__file__).parent / "data" / "parser_golden.json"
EVAL_FIELDS = ("building", "location", "ticket_type", "priority", "required_skill", "event_datetime")


def load_golden_cases() -> list[dict]:
    with GOLDEN_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def _field_metrics(cases: list[dict], field: str) -> dict[str, float]:
    true_positive = 0
    false_positive = 0
    false_negative = 0

    for case in cases:
        parser = get_ticket_parser()
        parsed = parser.parse(case["text"])
        expected = case["expected"].get(field)
        actual = parsed.get(field)

        if expected is not None:
            if actual == expected:
                true_positive += 1
            else:
                false_negative += 1
                if actual is not None:
                    false_positive += 1
        elif actual is not None:
            false_positive += 1

    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 1.0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 1.0
    return {"precision": precision, "recall": recall, "tp": true_positive, "fp": false_positive, "fn": false_negative}


@pytest.mark.parametrize("case", load_golden_cases(), ids=lambda case: f"case-{case['id']}")
def test_parser_golden_case(case: dict) -> None:
    parser = get_ticket_parser()
    parsed = parser.parse(case["text"])
    expected = case["expected"]

    for field in EVAL_FIELDS:
        if field in expected:
            assert parsed.get(field) == expected[field], (
                f"case {case['id']}: field {field}: expected {expected[field]!r}, got {parsed.get(field)!r}"
            )

    if "missing_fields" in case:
        for field in case["missing_fields"]:
            assert field in parsed["missing_fields"], (
                f"case {case['id']}: expected missing field {field!r}, got {parsed['missing_fields']}"
            )


def test_parser_field_metrics_thresholds() -> None:
    cases = load_golden_cases()
    metrics = {field: _field_metrics(cases, field) for field in EVAL_FIELDS}

    for field, values in metrics.items():
        assert values["precision"] >= 0.85, f"{field} precision too low: {values}"
        assert values["recall"] >= 0.85, f"{field} recall too low: {values}"
