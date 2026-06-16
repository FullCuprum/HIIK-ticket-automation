"""
Парсер текста заявок для извлечения структурированных полей.

Тестовые примеры:

Пример 1:
    "Срочно! Не работает интернет в ауд. 214, пользователи не могут выйти в сеть."
    -> location='214', problem_description='Не работает интернет',
       ticket_type='repair', priority='high', estimated_minutes=30,
       required_skill='network_engineer', missing_fields=[]

Пример 2:
    "В кабинете 105 нужно установить Microsoft Office."
    -> location='105', problem_description='установить Microsoft Office',
       ticket_type='software_installation', priority='low', estimated_minutes=45,
       required_skill='software_admin', missing_fields=[]

Пример 3:
    "Помогите, пожалуйста. В пятницу мероприятие, нужно настроить звук."
    -> location=None, problem_description='настроить звук на мероприятии',
       ticket_type='event_support', priority='low', estimated_minutes=120,
       required_skill='network_engineer', missing_fields=['location']
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from natasha import Segmenter
from pymorphy2 import MorphAnalyzer

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
    r"(?:ауд\.?\s*|каб\.?\s*|кабинет(?:е)?\s*|помещение\s*|офис\s*|аудитория\s*)"
    r"(\d+[А-Яа-я]?)",
    re.IGNORECASE,
)

TIME_ESTIMATES: dict[str, tuple[int, int]] = {
    "repair": (60, 30),
    "software_installation": (45, 20),
    "event_support": (120, 60),
    "other": (30, 15),
}

SKILL_BY_TYPE: dict[str, str] = {
    "repair": "hardware_support",
    "software_installation": "software_admin",
    "event_support": "network_engineer",
    "other": "general_support",
}


class TicketParser:
    """Извлекает структурированные поля из свободного текста заявки."""

    def __init__(self) -> None:
        try:
            # Natasha v1.6 не экспортирует класс Natasha; используем Segmenter + pymorphy2.
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
        """Загружает словарь телеком-терминов из JSON или возвращает встроенный."""
        default_vocabulary = {
            "problem_keywords": [
                "интернет",
                "wi-fi",
                "vpn",
                "принтер",
                "кросс",
                "патч-панель",
                "роутер",
                "коммутатор",
            ],
            "location_keywords": ["ауд", "каб", "помещение", "офис", "аудитория"],
            "urgency_keywords": ["срочно", "горит", "авария", "не работает", "всё упало"],
            "repair_keywords": ["ремонт", "сломалось", "не работает", "замена"],
            "software_keywords": [
                "установить",
                "установка по",
                "программное обеспечение",
                "microsoft office",
            ],
            "event_keywords": ["мероприятие", "конференция", "подключение к мероприятию"],
            "network_skill_keywords": ["vpn", "роутер", "интернет", "wi-fi", "сеть"],
        }

        try:
            if VOCABULARY_PATH.exists():
                with VOCABULARY_PATH.open(encoding="utf-8") as file:
                    return json.load(file)
        except Exception as exc:
            logger.warning("Failed to load telecom vocabulary from file: %s", exc)

        return default_vocabulary

    def extract_location(self, text: str) -> str | None:
        """Извлекает номер кабинета/аудитории из текста."""
        match = LOCATION_PATTERN.search(text)
        if match:
            return match.group(1)

        lowered = text.lower()
        for keyword in self.vocabulary.get("location_keywords", []):
            pattern = re.compile(
                rf"{re.escape(keyword)}\.?\s*(\d+[А-Яа-я]?)",
                re.IGNORECASE,
            )
            keyword_match = pattern.search(lowered)
            if keyword_match:
                return keyword_match.group(1)

        return None

    def extract_problem_description(self, text: str) -> str:
        """Возвращает краткое описание проблемы без служебных фраз."""
        result = text.strip()
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

        if any(keyword in original_lower for keyword in self.vocabulary.get("event_keywords", [])):
            if "мероприят" not in result.lower():
                result = f"{result} на мероприятии"

        if self.segmenter is not None:
            list(self.segmenter.tokenize(result))

        if len(result) > 100:
            result = result[:100].rsplit(" ", 1)[0]

        if result:
            return result[0].upper() + result[1:]

        return text[:100].strip()

    def detect_ticket_type(self, text: str) -> str:
        """Определяет тип заявки по ключевым словам."""
        lowered = text.lower()

        if self._contains_any(lowered, self.vocabulary.get("event_keywords", [])):
            return "event_support"
        if self._contains_any(lowered, self.vocabulary.get("software_keywords", [])):
            return "software_installation"
        if self._contains_any(lowered, self.vocabulary.get("repair_keywords", [])):
            return "repair"
        if self._contains_any(lowered, self.vocabulary.get("problem_keywords", [])):
            return "repair"

        return "other"

    def detect_priority(self, text: str) -> str:
        """Определяет срочность заявки."""
        lowered = text.lower()
        if self._contains_any(lowered, self.vocabulary.get("urgency_keywords", [])):
            return "high"
        return "low"

    def estimate_required_time(self, ticket_type: str, priority: str) -> int:
        """Оценивает требуемое время выполнения в минутах."""
        normal, urgent = TIME_ESTIMATES.get(ticket_type, TIME_ESTIMATES["other"])
        return urgent if priority == "high" else normal

    def determine_required_skill(self, ticket_type: str, problem_description: str) -> str:
        """Определяет требуемый навык исполнителя."""
        lowered = problem_description.lower()
        if self._contains_any(lowered, self.vocabulary.get("network_skill_keywords", [])):
            return "network_engineer"
        return SKILL_BY_TYPE.get(ticket_type, "general_support")

    def parse(self, raw_text: str) -> dict:
        """
        Основной метод парсинга заявки.

        Returns:
            dict с полями location, problem_description, ticket_type, priority,
            estimated_minutes, required_skill, missing_fields.
        """
        try:
            location = self.extract_location(raw_text)
            problem_description = self.extract_problem_description(raw_text)
            ticket_type = self.detect_ticket_type(raw_text)
            priority = self.detect_priority(raw_text)
            estimated_minutes = self.estimate_required_time(ticket_type, priority)
            required_skill = self.determine_required_skill(ticket_type, problem_description)

            missing_fields: list[str] = []
            if not location:
                missing_fields.append("location")
            if not problem_description.strip():
                missing_fields.append("problem_description")

            return {
                "location": location,
                "problem_description": problem_description,
                "ticket_type": ticket_type,
                "priority": priority,
                "estimated_minutes": estimated_minutes,
                "required_skill": required_skill,
                "missing_fields": missing_fields,
            }
        except Exception as exc:
            logger.exception("Ticket parsing failed")
            raise RuntimeError("Ticket parsing failed") from exc

    @staticmethod
    def _contains_any(text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)


@lru_cache
def get_ticket_parser() -> TicketParser:
    """Возвращает singleton-парсер, чтобы не перезагружать модели на каждый запрос."""
    return TicketParser()
