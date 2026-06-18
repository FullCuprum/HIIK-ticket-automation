from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.buildings import (
    ROOM_MARKER_PATTERN,
    normalize_room_number,
    resolve_building,
    validate_room_for_building,
)
from app.services.morphology import contains_keyword

LOCATION_INLINE_PATTERN = re.compile(
    r"(?:\s+в\s+)?"
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

STANDALONE_ROOM_PATTERN = re.compile(r"\b([1-5]\d{2}[А-Яа-я]?)\b")

NAMED_VENUE_PATTERN = re.compile(
    r"(?:в\s+)?"
    r"(актов\w+\s+зал\w*|компьютерн\w+\s+класс\w*)",
    re.IGNORECASE,
)

VAHTA_PATTERN = re.compile(r"\bна\s+вахте\b", re.IGNORECASE)

SECONDARY_LOCATION_CONTEXT = re.compile(
    r"(?:хранится|перевез\w*|перенест\w*|находится|из\s+стар\w*|из\s+аудитор\w*|"
    r"из\s+кабинет\w*|ip\s+\d)",
    re.IGNORECASE,
)

OPENING_BLOCK_SIZE = 280

VENUE_LABELS: dict[str, str] = {
    "актовый зал": "актовый зал",
    "актовом зале": "актовый зал",
    "актового зала": "актовый зал",
    "серверная": "серверная",
    "серверной": "серверная",
    "электрощитовая": "электрощитовая",
    "электрощитовой": "электрощитовая",
    "компьютерный класс": "компьютерный класс",
    "компьютерном классе": "компьютерный класс",
}

ENTITY_STRIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    LOCATION_INLINE_PATTERN,
    ROOM_MARKER_PATTERN,
    re.compile(
        r"(?:первый|второй|1|2)[-\s]?й?\s+корпус|"
        r"корпус\s+(?:во|спо)|"
        r"(?:первое|второе)\s+общежитие|"
        r"общежитие\s*(?:№\s*)?[12]|"
        r"ленина\s*,?\s*(?:56|58|60|73)",
        re.IGNORECASE,
    ),
    re.compile(r"\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\s+(?:в\s+)?\d{1,2}[:.]\d{2}", re.IGNORECASE),
    re.compile(
        r"\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
        r"(?:\s+\d{4})?(?:\s+(?:в\s+)?\d{1,2}[:.]\d{2})?",
        re.IGNORECASE,
    ),
)


@dataclass
class EntityExtractionResult:
    location: str | None = None
    building: str | None = None
    building_ambiguous: bool = False
    room_building_conflict: bool = False
    software_mentions: list[str] = field(default_factory=list)
    cleaned_text: str = ""


@dataclass(frozen=True)
class LocationCandidate:
    value: str
    position: int
    priority: int


def _normalize_venue_label(value: str) -> str:
    lowered = value.lower().strip()
    return VENUE_LABELS.get(lowered, lowered)


def _is_secondary_location(text: str, start: int) -> bool:
    before = text[max(0, start - 60) : start]
    return bool(SECONDARY_LOCATION_CONTEXT.search(before))


def _is_room_range(text: str, start: int, end: int) -> bool:
    after = text[end : end + 6]
    return bool(re.match(r"\s*-\s*\d", after))


def _collect_room_candidates(text: str) -> list[LocationCandidate]:
    candidates: list[LocationCandidate] = []

    for pattern in (ROOM_MARKER_PATTERN, LOCATION_INLINE_PATTERN):
        for match in pattern.finditer(text):
            if _is_secondary_location(text, match.start()):
                continue
            if _is_room_range(text, match.start(1), match.end(1)):
                continue

            room = normalize_room_number(match.group(1))
            if room:
                priority = 0 if match.start() < OPENING_BLOCK_SIZE else 1
                candidates.append(LocationCandidate(value=room, position=match.start(), priority=priority))

    for match in STANDALONE_ROOM_PATTERN.finditer(text):
        if _is_secondary_location(text, match.start()):
            continue
        if _is_room_range(text, match.start(), match.end()):
            continue

        before = text[max(0, match.start() - 8) : match.start()]
        if re.search(r"\d{3}\s*$", before):
            continue

        room = normalize_room_number(match.group(1))
        if room:
            priority = 2 if match.start() >= OPENING_BLOCK_SIZE else 1
            candidates.append(LocationCandidate(value=room, position=match.start(), priority=priority))

    return candidates


def _collect_venue_candidates(text: str) -> list[LocationCandidate]:
    candidates: list[LocationCandidate] = []

    for match in NAMED_VENUE_PATTERN.finditer(text):
        if _is_secondary_location(text, match.start()):
            continue

        label = _normalize_venue_label(match.group(1))
        priority = 0 if match.start() < OPENING_BLOCK_SIZE else 1
        candidates.append(LocationCandidate(value=label, position=match.start(), priority=priority))

    if VAHTA_PATTERN.search(text[:OPENING_BLOCK_SIZE]):
        match = VAHTA_PATTERN.search(text[:OPENING_BLOCK_SIZE])
        assert match is not None
        candidates.append(LocationCandidate(value="вахта", position=match.start(), priority=0))

    return candidates


def extract_location(text: str, vocabulary: dict[str, list[str]]) -> str | None:
    _ = vocabulary

    room_candidates = _collect_room_candidates(text)
    venue_candidates = _collect_venue_candidates(text)
    all_candidates = room_candidates + venue_candidates

    if not all_candidates:
        return None

    all_candidates.sort(key=lambda item: (item.priority, item.position))
    return all_candidates[0].value


def extract_software_mentions(text: str, vocabulary: dict[str, list[str]]) -> list[str]:
    software_names = vocabulary.get("software_names", [])
    mentions: list[str] = []
    lowered = text.lower()

    for name in software_names:
        if name.lower() in lowered or contains_keyword(text, name):
            mentions.append(name)

    return mentions


def build_cleaned_text(text: str, entities: EntityExtractionResult) -> str:
    cleaned = text
    for pattern in ENTITY_STRIP_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    for software in entities.software_mentions:
        cleaned = re.sub(re.escape(software), " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_entities(text: str, vocabulary: dict[str, list[str]]) -> EntityExtractionResult:
    location = extract_location(text, vocabulary)
    building, building_ambiguous = resolve_building(text, location if location and location.isdigit() else None)
    software_mentions = extract_software_mentions(text, vocabulary)

    room_building_conflict = False
    if location and location.isdigit() and building and not validate_room_for_building(location, building):
        room_building_conflict = True
        building = None
        building_ambiguous = True

    entities = EntityExtractionResult(
        location=location,
        building=building,
        building_ambiguous=building_ambiguous,
        room_building_conflict=room_building_conflict,
        software_mentions=software_mentions,
    )
    entities.cleaned_text = build_cleaned_text(text, entities)
    return entities
