from __future__ import annotations

import re

BUILDINGS: dict[str, str] = {
    "corpus_1": "Первый корпус (ВО, институт, Ленина 73)",
    "corpus_2": "Второй корпус (техникум, Ленина 58)",
    "dorm_1": "Общежитие 1 (Ленина 56)",
    "dorm_2": "Общежитие 2 (Ленина 60)",
}

BUILDING_KEYWORDS: dict[str, list[str]] = {
    "corpus_1": [
        "первый корпус",
        "первом корпусе",
        "первого корпуса",
        "1 корпус",
        "1-й корпус",
        "1 корпусе",
        "институт",
        "институте",
        "высшее образование",
        "ленина 73",
        "ленина, 73",
    ],
    "corpus_2": [
        "второй корпус",
        "втором корпусе",
        "второго корпуса",
        "2 корпус",
        "2-й корпус",
        "2 корпусе",
        "техникум",
        "техникуме",
        "ленина 58",
        "ленина, 58",
    ],
    "dorm_1": [
        "общежитие 1",
        "общежитии 1",
        "общежитие №1",
        "общежитии №1",
        "общежитие номер 1",
        "ленина 56",
        "ленина, 56",
    ],
    "dorm_2": [
        "общежитие 2",
        "общежитии 2",
        "общежитие №2",
        "общежитии №2",
        "общежитие номер 2",
        "ленина 60",
        "ленина, 60",
    ],
}

BUILDING_ADDRESS_PATTERNS: dict[str, re.Pattern[str]] = {
    code: re.compile(rf"ленина\s*[,]?\s*{address}\b", re.IGNORECASE)
    for code, address in {
        "corpus_1": "73",
        "corpus_2": "58",
        "dorm_1": "56",
        "dorm_2": "60",
    }.items()
}


def is_valid_building(value: str | None) -> bool:
    return bool(value and value in BUILDINGS)


def normalize_building(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    if cleaned in BUILDINGS:
        return cleaned

    lowered = cleaned.lower()
    for code, label in BUILDINGS.items():
        if lowered == label.lower():
            return code

    for code, keywords in BUILDING_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return code

    return None


def extract_building(text: str) -> str | None:
    lowered = text.lower()

    for code, pattern in BUILDING_ADDRESS_PATTERNS.items():
        if pattern.search(lowered):
            return code

    keyword_pairs: list[tuple[int, str, str]] = []
    for code, keywords in BUILDING_KEYWORDS.items():
        for keyword in keywords:
            keyword_pairs.append((len(keyword), keyword, code))

    for _length, keyword, code in sorted(keyword_pairs, reverse=True):
        if keyword in lowered:
            return code

    return None
