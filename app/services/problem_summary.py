from __future__ import annotations

import re

from app.services.buildings import BUILDING_KEYWORDS
from app.services.entities import EntityExtractionResult
from app.services.morphology import contains_keyword, get_morph_analyzer

NOISE_PHRASES = (
    "здравствуйте",
    "добрый день",
    "доброе утро",
    "привет",
    "помогите",
    "пожалуйста",
    "срочно",
    "горит",
)

PROBLEM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"проблема:\s*([^(\n.!?]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(прошу\s+подготовить\s+рабочее\s+место[^.!?\n]*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\b(?:перестал\w*|перестали)\s+[^,.!?\n]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"((?:не\s+работает|не\s+работают|не\s+включается|не\s+печатает|"
        r"не\s+записывает|не\s+видит|не\s+транслиру\w*|пропал\w*|сломал\w*)"
        r"(?:\s+[^,.!?\n]+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:прошу\s+)?(?:направить|обеспечить)\s+([^,.!?\n]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:нужно|необходимо|требуется)\s+([^,.!?\n]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"((?:установ\w+|настро\w+|подключ\w+|замен\w+|почин\w+|"
        r"подготов\w+|организ\w+|вывести|отремонтир\w+)\s+[^,.!?]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(техническ\w+\s+сопровожд\w+\s+[^,.!?]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(подготовк\w+\s+[^,.!?]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(консультац\w+\s+[^,.!?]+|подскаж\w+[^,.!?]*)",
        re.IGNORECASE,
    ),
)

LOCATION_NOISE_PATTERN = re.compile(
    r"(?:в\s+)?(?:"
    r"ауд\.?\s*|аудитор(?:ия|ии|ию|ией)\s*|"
    r"каб\.?\s*|кабинет(?:а|е|у|ом)?\s*|"
    r"комн(?:ата|аты|ате|ату|\.?)\s*|"
    r"пом(?:ещение|ещения|ещении|\.?)\s*|"
    r"офис(?:а|е|у|ом)?\s*"
    r")"
    r"[1-5]?\d{2,3}[А-Яа-я]?",
    re.IGNORECASE,
)

DATE_PATTERN = re.compile(
    r"\d{1,2}[./]\d{1,2}[./]\d{2,4}\s*(?:в\s+)?\d{1,2}[:.]\d{2}|"
    r"\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|"
    r"сентября|октября|ноября|декабря)\s+\d{4}(?:\s+(?:в\s+)?\d{1,2}[:.]\d{2})?",
    re.IGNORECASE,
)

WEEKDAY_PATTERN = re.compile(
    r"(?:в\s+)?(?:понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)[,.]?\s*",
    re.IGNORECASE,
)

TRAILING_BUILDING_PATTERN = re.compile(
    r",?\s*(?:первого|второго|первом|втором|1|2)[-\s]?го?\s+корпуса?\b.*$",
    re.IGNORECASE,
)

DORM_TAIL_PATTERN = re.compile(
    r",?\s*общежит(?:ие|ия|ии|ии)\s*(?:№\s*)?[12]\b.*$",
    re.IGNORECASE,
)

INSTALL_VERB_PATTERN = re.compile(r"^установ\w+\s+", re.IGNORECASE)
SETUP_VERB_PATTERN = re.compile(r"^настро\w+\s+", re.IGNORECASE)

from app.services.ticket_types import TICKET_TYPE_LABELS

TYPE_FALLBACKS: dict[str, str] = {
    **TICKET_TYPE_LABELS,
    "repair": "Ремонт оборудования",
    "software_installation": "Установка программного обеспечения",
    "event_support": "Сопровождение мероприятия",
}


ORPHAN_LOCATION_PATTERN = re.compile(
    r"\s+в\s+(?:"
    r"ауд\.?|каб\.?|кабинет\w*|комнат\w*|пом\w*|офис\w*|"
    r"аудитор\w*"
    r")\b\.?",
    re.IGNORECASE,
)

CONTEXT_LOCATION_PATTERN = re.compile(
    r"\s+на\s+вахте\b|\s+в\s+коридоре\b",
    re.IGNORECASE,
)

BUILDING_STRIP_KEYWORDS: list[str] = []
for code, items in BUILDING_KEYWORDS.items():
    for keyword in items:
        if keyword not in {"вахта", "на вахте", "коридор", "коридоре", "в коридоре"}:
            BUILDING_STRIP_KEYWORDS.append(keyword)
BUILDING_STRIP_KEYWORDS.sort(key=len, reverse=True)
BUILDING_NOISE_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(keyword) for keyword in BUILDING_STRIP_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

EVENT_NAME_PATTERN = re.compile(r"состоится\s+([^.\n]+)", re.IGNORECASE)
EVENT_HINT_PATTERN = re.compile(r"мероприят|вебинар|конференц|презентац", re.IGNORECASE)

WORKSPACE_PREP_PATTERN = re.compile(r"подготов\w*\s+рабоч\w*\s+мест\w*", re.IGNORECASE)


def _capitalize(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    return text[0].upper() + text[1:]


def _normalize_install_phrase(phrase: str) -> str:
    phrase = INSTALL_VERB_PATTERN.sub("", phrase).strip()
    if phrase:
        return _capitalize(f"Установка {phrase}")
    return TYPE_FALLBACKS["software_installation"]


def _normalize_setup_phrase(phrase: str) -> str:
    return _capitalize(phrase)


def _extract_context_location(raw_text: str) -> str | None:
    match = CONTEXT_LOCATION_PATTERN.search(raw_text)
    if match:
        return match.group(0).strip()
    return None


def sanitize_problem_phrase(phrase: str) -> str:
    result = phrase.strip()

    for noise in NOISE_PHRASES:
        result = re.sub(rf"\b{re.escape(noise)}\b", "", result, flags=re.IGNORECASE)

    result = LOCATION_NOISE_PATTERN.sub("", result)
    result = ORPHAN_LOCATION_PATTERN.sub("", result)
    result = BUILDING_NOISE_PATTERN.sub("", result)
    result = DATE_PATTERN.sub("", result)
    result = WEEKDAY_PATTERN.sub("", result)
    result = TRAILING_BUILDING_PATTERN.sub("", result)
    result = DORM_TAIL_PATTERN.sub("", result)
    result = re.sub(r"\([^)]*\)", "", result)
    result = re.sub(r"пользователи.*", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\b(?:ленина\s*,?\s*)?(?:56|58|60|73)\b", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\b(?:институт|техникум)\b", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\s+\d{1,2}\s+(?:в\s+)?\d{1,2}\b", " ", result)
    result = re.sub(r"\s+\d{1,2}\b$", "", result)
    result = re.sub(r"\s+", " ", result).strip(" .,;!?-")

    return result


def _truncate_description(text: str, max_len: int = 100) -> str:
    if len(text) <= max_len:
        return text

    cut = text[:max_len].rsplit(" ", 1)[0]
    cut = re.sub(r"\([^)]*$", "", cut).strip(" ,;:-")
    return cut


def _extract_event_title(raw_text: str) -> str | None:
    match = EVENT_NAME_PATTERN.search(raw_text)
    if not match:
        return None

    title = sanitize_problem_phrase(match.group(1).strip())
    return title or None


def extract_problem_phrase(raw_text: str) -> str | None:
    workspace_match = WORKSPACE_PREP_PATTERN.search(raw_text)
    if workspace_match:
        phrase = sanitize_problem_phrase(workspace_match.group(0))
        if len(phrase) >= 3:
            return phrase

    for pattern in PROBLEM_PATTERNS:
        match = pattern.search(raw_text)
        if not match:
            continue

        phrase = sanitize_problem_phrase(match.group(1) if match.lastindex else match.group(0))
        if len(phrase) >= 3:
            return phrase

    return None


def _compose_from_type(
    ticket_type: str | None,
    entities: EntityExtractionResult,
    phrase: str | None,
    raw_text: str,
    location: str | None,
) -> str | None:
    if ticket_type == "software_installation" and entities.software_mentions:
        software = entities.software_mentions[0]
        if phrase and software.lower() in phrase.lower():
            if INSTALL_VERB_PATTERN.search(phrase):
                return _normalize_install_phrase(phrase)
            return _capitalize(f"Установка {software}")
        return _capitalize(f"Установка {software}")

    if ticket_type == "event_support":
        event_title = _extract_event_title(raw_text)
        if event_title:
            return _capitalize(f"Сопровождение: {event_title}")

        if phrase:
            normalized = _normalize_setup_phrase(phrase) if SETUP_VERB_PATTERN.match(phrase) else _capitalize(phrase)
            if not EVENT_HINT_PATTERN.search(normalized):
                normalized = f"{normalized} на мероприятии"
            return normalized
        return TYPE_FALLBACKS["event_support"]

    if ticket_type == "workspace_setup" and WORKSPACE_PREP_PATTERN.search(raw_text):
        if re.search(r"нов\w+\s+преподавател\w*", raw_text, re.IGNORECASE):
            return "Подготовка рабочего места нового преподавателя"
        if phrase:
            normalized = _capitalize(phrase)
            if normalized.lower().startswith("подготовить"):
                return normalized.replace("Подготовить", "Подготовка", 1)
            return normalized
        return TYPE_FALLBACKS["workspace_setup"]

    if ticket_type == "consultation" and phrase:
        return _capitalize(phrase)

    if ticket_type == "video_surveillance" and phrase:
        return _capitalize(phrase)

    if ticket_type == "other" and WORKSPACE_PREP_PATTERN.search(raw_text):
        if re.search(r"нов\w+\s+преподавател\w*", raw_text, re.IGNORECASE):
            return "Подготовка рабочего места нового преподавателя"
        if phrase:
            normalized = _capitalize(phrase)
            if normalized.lower().startswith("подготовить"):
                return normalized.replace("Подготовить", "Подготовка", 1)
            return normalized

    if ticket_type == "software_installation" and WORKSPACE_PREP_PATTERN.search(raw_text):
        workspace_match = WORKSPACE_PREP_PATTERN.search(raw_text)
        if workspace_match:
            return _capitalize(sanitize_problem_phrase(workspace_match.group(0)))

    if phrase:
        if ticket_type == "software_installation" and INSTALL_VERB_PATTERN.search(phrase):
            return _normalize_install_phrase(phrase)
        if SETUP_VERB_PATTERN.match(phrase):
            return _normalize_setup_phrase(phrase)

        normalized = _capitalize(phrase)
        if not location:
            context_location = _extract_context_location(raw_text)
            if context_location and context_location.lower() not in normalized.lower():
                normalized = f"{normalized} {context_location}"
        return normalized

    return TYPE_FALLBACKS.get(ticket_type or "other")


def compose_problem_description(
    raw_text: str,
    ticket_type: str | None,
    entities: EntityExtractionResult,
    vocabulary: dict[str, list[str]],
) -> str:
    morph = get_morph_analyzer()
    phrase = extract_problem_phrase(raw_text)

    if not phrase:
        for field_name in ("repair_keywords", "software_keywords", "event_keywords", "workspace_keywords"):
            for keyword in vocabulary.get(field_name, []):
                if contains_keyword(raw_text, keyword, morph):
                    phrase = sanitize_problem_phrase(keyword)
                    break
            if phrase:
                break

    description = _compose_from_type(
        ticket_type,
        entities,
        phrase,
        raw_text,
        entities.location,
    )
    if not description:
        description = raw_text[:100].strip()

    if len(description) > 100:
        description = _truncate_description(description)

    return description
