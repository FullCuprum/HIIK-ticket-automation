"""
Парсер текста заявок для извлечения структурированных полей.

Двухэтапный разбор:
1. NER/regex — здание, кабинет, дата, ПО (entities.py)
2. Классификация типа по очищенному тексту (ticket_type_classifier.py)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from natasha import Segmenter
from pymorphy2 import MorphAnalyzer

from app.services.buildings import resolve_building
from app.services.entities import extract_entities, extract_location as extract_location_entity
from app.services.event_support import EVENT_TOTAL_MINUTES, apply_event_support_defaults
from app.services.morphology import contains_keyword
from app.services.problem_summary import compose_problem_description
from app.services.ticket_type_classifier import classify_ticket_type
from app.services.ticket_types import SKILL_BY_TYPE, TIME_ESTIMATES
from app.utils.datetime_utils import get_app_timezone, now_local

logger = logging.getLogger(__name__)

VOCABULARY_PATH = Path(__file__).parent / "data" / "telecom_vocabulary.json"

NOISE_PHRASES = (
    "здравствуйте",
    "добрый день",
    "доброе утро",
    "привет",
    "помогите",
    "пожалуйста",
)

LOCATION_PATTERN = re.compile(
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


MONTHS_RU: dict[str, int] = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

EVENT_DATETIME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})\s+(?:в\s+)?(\d{1,2})[:.](\d{2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,2})\s+(" + "|".join(MONTHS_RU.keys()) + r")\s+(\d{4})\s+(?:в\s+)?(\d{1,2})[:.](\d{2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,2})[./](\d{1,2})\s+(?:в\s+)?(\d{1,2})[:.](\d{2})",
        re.IGNORECASE,
    ),
)

EVENT_DAY_MONTH_PATTERN = re.compile(
    r"(\d{1,2})\s+(" + "|".join(MONTHS_RU.keys()) + r")(?:\s+(\d{4}))?\b",
    re.IGNORECASE,
)

EVENT_TIME_PATTERN = re.compile(r"\bс\s+(\d{1,2})[:.](\d{2})\b", re.IGNORECASE)


class TicketParser:
    """Извлекает структурированные поля из свободного текста заявки."""

    def __init__(self) -> None:
        try:
            self.segmenter = Segmenter()
            try:
                self.morph = MorphAnalyzer()
            except Exception as morph_exc:
                logger.warning("MorphAnalyzer unavailable: %s", morph_exc)
                self.morph = None
            self.vocabulary = self.load_telecom_vocabulary()
        except Exception as exc:
            logger.exception("Failed to initialize TicketParser")
            raise RuntimeError("TicketParser initialization failed") from exc

    @staticmethod
    def load_telecom_vocabulary() -> dict[str, list[str]]:
        default_vocabulary: dict[str, list[str]] = {
            "problem_keywords": ["интернет", "принтер", "коммутатор"],
            "location_keywords": ["ауд", "каб", "кабинет", "помещение"],
            "urgency_keywords": ["срочно", "не работает"],
            "repair_keywords": ["ремонт", "сломалось"],
            "software_keywords": ["установить", "office"],
            "event_keywords": ["мероприятие", "конференция"],
            "workspace_keywords": ["рабочее место"],
            "network_skill_keywords": ["интернет", "wi-fi"],
            "software_names": ["Microsoft Office"],
            "negative_rules": [],
        }

        try:
            if VOCABULARY_PATH.exists():
                with VOCABULARY_PATH.open(encoding="utf-8") as file:
                    return json.load(file)
        except Exception as exc:
            logger.warning("Failed to load telecom vocabulary from file: %s", exc)

        return default_vocabulary

    def extract_location(self, text: str) -> str | None:
        return extract_location_entity(text, self.vocabulary)

    def extract_building(self, text: str, location: str | None = None) -> str | None:
        building, ambiguous = resolve_building(text, location)
        if ambiguous:
            return None
        return building

    def extract_problem_description(
        self,
        text: str,
        ticket_type: str | None = None,
        entities: object | None = None,
        cleaned_text: str | None = None,
    ) -> str:
        if entities is not None:
            return compose_problem_description(text, ticket_type, entities, self.vocabulary)

        source = cleaned_text or text
        result = source.strip()
        original_lower = text.lower()

        for phrase in NOISE_PHRASES:
            result = re.sub(rf"\b{re.escape(phrase)}\b", "", result, flags=re.IGNORECASE)

        result = re.sub(r"^\s*срочно[!.,]?\s*", "", result, flags=re.IGNORECASE)
        result = re.sub(r"^\s*горит[!.,]?\s*", "", result, flags=re.IGNORECASE)
        result = LOCATION_PATTERN.sub("", result)
        result = re.sub(r"пользователи.*", "", result, flags=re.IGNORECASE)
        result = re.sub(
            r"в\s+(?:понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)[,.]?\s*",
            "",
            result,
            flags=re.IGNORECASE,
        )
        result = re.sub(r"в\s+\w+\s+неделю[,.]?\s*", "", result, flags=re.IGNORECASE)
        result = re.sub(r"^в\s+", "", result, flags=re.IGNORECASE)
        result = re.sub(r"нужно\s+", "", result, flags=re.IGNORECASE)
        result = re.sub(r"мероприятие,?\s*", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s+в\s*$", "", result, flags=re.IGNORECASE)
        result = re.sub(r",\s*$", "", result)
        result = re.sub(r"\s+", " ", result).strip(" .,!")

        if any(
            contains_keyword(original_lower, keyword, self.morph)
            for keyword in self.vocabulary.get("event_keywords", [])
        ):
            if "мероприят" not in result.lower():
                result = f"{result} на мероприятии"

        if self.segmenter is not None:
            list(self.segmenter.tokenize(result))

        if len(result) > 100:
            result = result[:100].rsplit(" ", 1)[0]

        if result:
            return result[0].upper() + result[1:]

        return text[:100].strip()

    def detect_ticket_type(self, text: str, cleaned_text: str | None = None) -> str:
        entities = extract_entities(text, self.vocabulary)
        classification = classify_ticket_type(
            text,
            cleaned_text or entities.cleaned_text,
            entities,
            self.vocabulary,
        )
        return classification.ticket_type or "other"

    def detect_priority(self, text: str, ticket_type: str | None = None) -> str:
        if ticket_type == "event_support":
            return "high"

        if any(
            contains_keyword(text, keyword, self.morph)
            for keyword in self.vocabulary.get("urgency_keywords", [])
        ):
            return "high"
        return "low"

    def estimate_required_time(self, ticket_type: str, priority: str) -> int:
        if ticket_type == "event_support":
            return EVENT_TOTAL_MINUTES

        normal, urgent = TIME_ESTIMATES.get(ticket_type, TIME_ESTIMATES["other"])
        return urgent if priority == "high" else normal

    def extract_event_datetime(self, text: str) -> datetime | None:
        lowered = text.lower()
        tz = get_app_timezone()
        now = now_local()

        for pattern in EVENT_DATETIME_PATTERNS:
            match = pattern.search(lowered)
            if not match:
                continue

            groups = match.groups()
            try:
                if len(groups) == 5 and groups[1] in MONTHS_RU:
                    day = int(groups[0])
                    month = MONTHS_RU[groups[1]]
                    year = int(groups[2])
                    hour = int(groups[3])
                    minute = int(groups[4])
                elif len(groups) == 5:
                    day = int(groups[0])
                    month = int(groups[1])
                    year = int(groups[2])
                    if year < 100:
                        year += 2000
                    hour = int(groups[3])
                    minute = int(groups[4])
                elif len(groups) == 4:
                    day = int(groups[0])
                    month = int(groups[1])
                    year = now.year
                    hour = int(groups[2])
                    minute = int(groups[3])
                else:
                    continue

                candidate = datetime(year, month, day, hour, minute, tzinfo=tz)
                if candidate < now - timedelta(days=1):
                    continue
                return candidate
            except ValueError:
                continue

        day_month_match = EVENT_DAY_MONTH_PATTERN.search(lowered)
        if day_month_match:
            try:
                day = int(day_month_match.group(1))
                month = MONTHS_RU[day_month_match.group(2)]
                year = int(day_month_match.group(3)) if day_month_match.group(3) else now.year
                hour, minute = 9, 0
                time_match = EVENT_TIME_PATTERN.search(lowered)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2))

                candidate = datetime(year, month, day, hour, minute, tzinfo=tz)
                if candidate < now - timedelta(days=1) and not day_month_match.group(3):
                    candidate = candidate.replace(year=year + 1)
                if candidate >= now - timedelta(days=1):
                    return candidate
            except ValueError:
                pass

        return None

    def determine_required_skill(
        self,
        ticket_type: str,
        problem_description: str,
        raw_text: str = "",
    ) -> str:
        if ticket_type == "event_support":
            return "event_support"

        if ticket_type == "consultation":
            return "general_support"

        if ticket_type == "video_surveillance":
            return "hardware_support"

        if ticket_type in {"other", "workspace_setup"} and re.search(
            r"подготов\w*\s+рабоч", raw_text, re.IGNORECASE
        ):
            return "general_support"

        combined = f"{problem_description} {raw_text}"
        if any(
            contains_keyword(combined, keyword, self.morph)
            for keyword in self.vocabulary.get("network_skill_keywords", [])
        ):
            return "network_engineer"
        return SKILL_BY_TYPE.get(ticket_type, "general_support")

    def parse(self, raw_text: str) -> dict:
        try:
            entities = extract_entities(raw_text, self.vocabulary)
            classification = classify_ticket_type(
                raw_text,
                entities.cleaned_text,
                entities,
                self.vocabulary,
            )

            location = entities.location
            building = entities.building
            ticket_type = classification.ticket_type
            problem_description = self.extract_problem_description(
                raw_text,
                ticket_type=ticket_type,
                entities=entities,
            )
            priority = self.detect_priority(raw_text, ticket_type)
            estimated_minutes = self.estimate_required_time(ticket_type or "other", priority)
            required_skill = self.determine_required_skill(
                ticket_type or "other",
                problem_description,
                raw_text,
            )
            event_datetime = (
                self.extract_event_datetime(raw_text) if ticket_type == "event_support" else None
            )

            result = {
                "location": location,
                "building": building,
                "problem_description": problem_description,
                "ticket_type": ticket_type,
                "priority": priority,
                "estimated_minutes": estimated_minutes,
                "required_skill": required_skill,
                "event_datetime": event_datetime.isoformat() if event_datetime else None,
                "missing_fields": [],
            }
            result = apply_event_support_defaults(result)

            missing_fields: list[str] = []
            if not building or entities.building_ambiguous or entities.room_building_conflict:
                missing_fields.append("building")
            if not location:
                missing_fields.append("location")
            if not problem_description.strip():
                missing_fields.append("problem_description")
            if classification.ambiguous or not ticket_type:
                missing_fields.append("ticket_type")
            if ticket_type == "event_support" and not event_datetime:
                missing_fields.append("event_datetime")

            result["missing_fields"] = missing_fields
            return result
        except Exception as exc:
            logger.exception("Ticket parsing failed")
            raise RuntimeError("Ticket parsing failed") from exc


@lru_cache
def get_ticket_parser() -> TicketParser:
    return TicketParser()
