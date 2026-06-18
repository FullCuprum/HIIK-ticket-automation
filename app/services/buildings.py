from __future__ import annotations

import re
from dataclasses import dataclass

BUILDINGS: dict[str, str] = {
    "corpus_1": "Корпус ВО (первый корпус, Ленина 73)",
    "corpus_2": "Корпус СПО (второй корпус, Ленина 58)",
    "dorm_1": "Первое общежитие (Ленина 56)",
    "dorm_2": "Второе общежитие (Ленина 60)",
}

BUILDING_META: dict[str, dict[str, int | str]] = {
    "corpus_1": {"floors": 4, "address": "73", "kind": "corpus"},
    "corpus_2": {"floors": 4, "address": "58", "kind": "corpus"},
    "dorm_1": {"floors": 5, "address": "56", "kind": "dorm"},
    "dorm_2": {"floors": 5, "address": "60", "kind": "dorm"},
}

BUILDING_KEYWORDS: dict[str, list[str]] = {
    "corpus_1": [
        "первый корпус",
        "первом корпусе",
        "первого корпуса",
        "1 корпус",
        "1-й корпус",
        "1 корпусе",
        "корпус во",
        "корпус высшего образования",
        "высшее образование",
        "высшего образования",
        "институт",
        "институте",
        "института",
        "ленина 73",
        "ленина, 73",
        "ул. ленина 73",
    ],
    "corpus_2": [
        "второй корпус",
        "втором корпусе",
        "второго корпуса",
        "2 корпус",
        "2-й корпус",
        "2 корпусе",
        "корпус спо",
        "среднее профессиональное образование",
        "среднего профессионального образования",
        "техникум",
        "техникуме",
        "техникума",
        "ленина 58",
        "ленина, 58",
        "ул. ленина 58",
    ],
    "dorm_1": [
        "первое общежитие",
        "первом общежитии",
        "первого общежития",
        "общежитие 1",
        "общежитии 1",
        "общежития 1",
        "общежитие №1",
        "общежитии №1",
        "общежитие номер 1",
        "общежитие № 1",
        "общежитии № 1",
        "ленина 56",
        "ленина, 56",
        "ул. ленина 56",
        "вахта",
        "на вахте",
    ],
    "dorm_2": [
        "второе общежитие",
        "втором общежитии",
        "второго общежития",
        "общежитие 2",
        "общежитии 2",
        "общежития 2",
        "общежитие №2",
        "общежитии №2",
        "общежитие № 2",
        "общежитии № 2",
        "общежитие номер 2",
        "ленина 60",
        "ленина, 60",
        "ул. ленина 60",
    ],
}

BUILDING_ADDRESS_PATTERNS: dict[str, re.Pattern[str]] = {
    code: re.compile(rf"ленина\s*[,]?\s*{meta['address']}\b", re.IGNORECASE)
    for code, meta in BUILDING_META.items()
}

MULTI_CORPUS_PATTERN = re.compile(
    r"перв\w*.*втор\w*|втор\w*.*перв\w*",
    re.IGNORECASE,
)

ROOM_STRICT_PATTERN = re.compile(r"\b([1-5])(\d{2})([А-Яа-я]?)\b")
ROOM_MARKER_PATTERN = re.compile(
    r"(?:"
    r"ауд\.?\s*|аудитор(?:ия|ии|ию|ией)\s*|"
    r"каб\.?\s*|кабинет(?:а|е|у|ом)?\s*|"
    r"комн(?:ата|аты|ате|ату|\.?)\s*|"
    r"пом(?:ещение|ещения|ещении|\.?)\s*|"
    r"офис(?:а|е|у|ом)?\s*"
    r")"
    r"([1-5]\d{2}[А-Яа-я]?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BuildingMatch:
    code: str
    score: int
    source: str


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


def parse_room_number(value: str | None) -> tuple[int, int, str] | None:
    if not value:
        return None

    match = ROOM_STRICT_PATTERN.fullmatch(value.strip())
    if not match:
        digits = re.sub(r"[^0-9]", "", value)
        if len(digits) == 3:
            match = ROOM_STRICT_PATTERN.fullmatch(digits)
        if not match:
            return None

    floor = int(match.group(1))
    room = int(match.group(2))
    suffix = match.group(3) or ""
    return floor, room, f"{floor}{room:02d}{suffix}"


def room_floor(value: str | None) -> int | None:
    parsed = parse_room_number(value)
    return parsed[0] if parsed else None


def normalize_room_number(value: str | None) -> str | None:
    parsed = parse_room_number(value)
    return parsed[2] if parsed else None


def max_floors_for_building(building_code: str | None) -> int | None:
    if not building_code:
        return None
    meta = BUILDING_META.get(building_code)
    return int(meta["floors"]) if meta else None


def buildings_matching_room(room: str | None) -> list[str]:
    parsed = parse_room_number(room)
    if parsed is None:
        return []

    floor, _, _ = parsed
    matches: list[str] = []
    for code, meta in BUILDING_META.items():
        if 1 <= floor <= int(meta["floors"]):
            matches.append(code)
    return matches


def validate_room_for_building(room: str | None, building_code: str | None) -> bool:
    if not room or not building_code:
        return True

    parsed = parse_room_number(room)
    if parsed is None:
        return False

    floor, room_on_floor, _ = parsed
    max_floors = max_floors_for_building(building_code)
    if max_floors is None:
        return False
    if floor < 1 or floor > max_floors:
        return False
    return 1 <= room_on_floor <= 99


def extract_building_candidates(text: str) -> list[BuildingMatch]:
    lowered = text.lower()
    candidates: dict[str, BuildingMatch] = {}

    for code, pattern in BUILDING_ADDRESS_PATTERNS.items():
        if pattern.search(lowered):
            candidates[code] = BuildingMatch(code=code, score=5, source="address")

    keyword_pairs: list[tuple[int, str, str]] = []
    for code, keywords in BUILDING_KEYWORDS.items():
        for keyword in keywords:
            keyword_pairs.append((len(keyword), keyword, code))

    for _length, keyword, code in sorted(keyword_pairs, reverse=True):
        if keyword in lowered:
            current = candidates.get(code)
            score = 3 + min(len(keyword) // 8, 2)
            if current is None or score > current.score:
                candidates[code] = BuildingMatch(code=code, score=score, source="keyword")

    return sorted(candidates.values(), key=lambda item: item.score, reverse=True)


def count_distinct_building_mentions(text: str) -> set[str]:
    lowered = text.lower()
    mentioned: set[str] = set()

    if "корпус" in lowered and MULTI_CORPUS_PATTERN.search(lowered):
        mentioned.update({"corpus_1", "corpus_2"})

    for code, pattern in BUILDING_ADDRESS_PATTERNS.items():
        if pattern.search(lowered):
            mentioned.add(code)

    keyword_pairs: list[tuple[int, str, str]] = []
    for code, keywords in BUILDING_KEYWORDS.items():
        for keyword in keywords:
            keyword_pairs.append((len(keyword), keyword, code))

    for _length, keyword, code in sorted(keyword_pairs, reverse=True):
        if keyword in lowered:
            mentioned.add(code)

    return mentioned


def resolve_building(text: str, room: str | None = None) -> tuple[str | None, bool]:
    """Возвращает код здания и флаг неоднозначности."""
    mentioned = count_distinct_building_mentions(text)
    if len(mentioned) > 1:
        return None, True

    candidates = extract_building_candidates(text)

    if room:
        room_buildings = buildings_matching_room(room)
        if room_buildings:
            filtered = [item for item in candidates if item.code in room_buildings]
            if filtered:
                candidates = filtered
            elif len(room_buildings) == 1:
                return room_buildings[0], False

    if not candidates:
        if room and len(buildings_matching_room(room)) == 1:
            return buildings_matching_room(room)[0], False
        return None, False

    if len(candidates) == 1:
        return candidates[0].code, False

    if candidates[0].score > candidates[1].score:
        return candidates[0].code, False

    top_codes = {item.code for item in candidates if item.score == candidates[0].score}
    if len(top_codes) == 1:
        return candidates[0].code, False

    return None, True


def extract_building(text: str) -> str | None:
    building, ambiguous = resolve_building(text)
    if ambiguous:
        return None
    return building
