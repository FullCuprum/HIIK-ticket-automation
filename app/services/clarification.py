from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.services.event_support import apply_event_support_defaults
from app.services.parser import get_ticket_parser

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 24 * 60 * 60

REQUIRED_FIELDS = (
    "building",
    "location",
    "problem_description",
    "ticket_type",
    "priority",
    "estimated_minutes",
    "required_skill",
)

FIELD_QUESTIONS: dict[str, str] = {
    "building": "Укажите здание: первый корпус, второй корпус, общежитие 1 или общежитие 2.",
    "location": "Укажите номер кабинета, где возникла проблема.",
    "problem_description": "Опишите подробнее, в чём заключается проблема.",
    "ticket_type": "Уточните тип заявки: ремонт, установка ПО или сопровождение мероприятия.",
    "priority": "Укажите срочность заявки: low или high.",
    "estimated_minutes": "Укажите ориентировочное время выполнения в минутах.",
    "required_skill": "Укажите требуемый навык исполнителя.",
    "event_datetime": "Укажите дату и время мероприятия.",
}


class ClarificationService:
    """Управляет диалогом уточнения заявки через Redis-сессии."""

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    @staticmethod
    def _session_key(ticket_id: int) -> str:
        return f"clarify:{ticket_id}"

    @staticmethod
    def normalize_extracted(extracted: dict[str, Any]) -> dict[str, Any]:
        """Приводит extracted к единому набору обязательных полей."""
        return {
            "building": extracted.get("building"),
            "location": extracted.get("location"),
            "problem_description": extracted.get("problem_description"),
            "ticket_type": extracted.get("ticket_type"),
            "priority": extracted.get("priority"),
            "estimated_minutes": extracted.get("estimated_minutes"),
            "required_skill": extracted.get("required_skill"),
            "event_datetime": extracted.get("event_datetime"),
        }

    @classmethod
    def _required_fields(cls, extracted: dict[str, Any]) -> tuple[str, ...]:
        fields: list[str] = list(REQUIRED_FIELDS)
        if extracted.get("ticket_type") == "event_support":
            fields.append("event_datetime")
        return tuple(fields)

    @classmethod
    def compute_missing_fields(cls, extracted: dict[str, Any]) -> list[str]:
        """Проверяет, какие обязательные поля ещё не заполнены."""
        missing_fields: list[str] = []
        for field in cls._required_fields(extracted):
            value = extracted.get(field)
            if value is None:
                missing_fields.append(field)
            elif isinstance(value, str) and not value.strip():
                missing_fields.append(field)
        return missing_fields

    @classmethod
    def fill_derived_fields(cls, extracted: dict[str, Any]) -> dict[str, Any]:
        """Дополняет derived-поля на основе уже известных данных."""
        parser = get_ticket_parser()
        result = cls.normalize_extracted(extracted)
        result = apply_event_support_defaults(result)

        if not result.get("priority"):
            result["priority"] = "low"

        ticket_type = result.get("ticket_type")
        priority = result.get("priority", "low")
        problem_description = result.get("problem_description") or ""

        if ticket_type and result.get("estimated_minutes") is None:
            result["estimated_minutes"] = parser.estimate_required_time(ticket_type, priority)

        if ticket_type and not result.get("required_skill"):
            result["required_skill"] = parser.determine_required_skill(
                ticket_type, problem_description
            )

        return result

    @classmethod
    def generate_question(cls, missing_fields: list[str]) -> str:
        """Возвращает общий вопрос для нескольких отсутствующих полей."""
        if not missing_fields:
            return ""

        if len(missing_fields) == 1:
            return cls._question_for_field(missing_fields[0])

        labels = [cls._field_label(field) for field in missing_fields]
        return f"Уточните, пожалуйста: {', '.join(labels)}."

    @classmethod
    def generate_questions(cls, missing_fields: list[str]) -> list[str]:
        """Возвращает список вопросов для пользователя."""
        if not missing_fields:
            return []
        if len(missing_fields) == 1:
            return [cls._question_for_field(missing_fields[0])]
        return [cls.generate_question(missing_fields)]

    async def create_session(
        self,
        ticket_id: int,
        extracted: dict[str, Any],
        missing_fields: list[str],
    ) -> int:
        """Создаёт Redis-сессию уточнения и возвращает ticket_id."""
        normalized = self.fill_derived_fields(extracted)
        missing_fields = self.compute_missing_fields(normalized)
        questions = self.generate_questions(missing_fields)
        payload = {
            "ticket_id": ticket_id,
            "extracted": normalized,
            "missing_fields": missing_fields,
            "last_question": questions[0] if questions else "",
        }

        try:
            await self.redis.set(
                self._session_key(ticket_id),
                json.dumps(payload, ensure_ascii=False),
                ex=SESSION_TTL_SECONDS,
            )
            logger.info("Created clarification session for ticket_id=%s", ticket_id)
        except RedisError as exc:
            logger.exception("Failed to create clarification session for ticket_id=%s", ticket_id)
            raise RuntimeError("Failed to create clarification session") from exc

        return ticket_id

    async def get_session(self, ticket_id: int) -> dict[str, Any] | None:
        """Получает данные сессии из Redis."""
        try:
            raw = await self.redis.get(self._session_key(ticket_id))
        except RedisError as exc:
            logger.exception("Failed to read clarification session for ticket_id=%s", ticket_id)
            raise RuntimeError("Failed to read clarification session") from exc

        if not raw:
            return None

        return json.loads(raw)

    async def update_session(
        self,
        ticket_id: int,
        new_extracted: dict[str, Any],
    ) -> dict[str, Any]:
        """Обновляет extracted-поля и пересчитывает missing_fields."""
        session = await self.get_session(ticket_id)
        if session is None:
            raise ValueError(f"Clarification session not found for ticket_id={ticket_id}")

        merged = self.normalize_extracted(session.get("extracted", {}))
        merged.update({key: value for key, value in new_extracted.items() if value is not None})
        merged = self.fill_derived_fields(merged)

        missing_fields = self.compute_missing_fields(merged)
        questions = self.generate_questions(missing_fields)
        payload = {
            "ticket_id": ticket_id,
            "extracted": merged,
            "missing_fields": missing_fields,
            "last_question": questions[0] if questions else "",
        }

        try:
            await self.redis.set(
                self._session_key(ticket_id),
                json.dumps(payload, ensure_ascii=False),
                ex=SESSION_TTL_SECONDS,
            )
            logger.info(
                "Updated clarification session for ticket_id=%s, missing_fields=%s",
                ticket_id,
                missing_fields,
            )
        except RedisError as exc:
            logger.exception("Failed to update clarification session for ticket_id=%s", ticket_id)
            raise RuntimeError("Failed to update clarification session") from exc

        return payload

    async def delete_session(self, ticket_id: int) -> None:
        """Удаляет сессию после успешного завершения диалога."""
        try:
            await self.redis.delete(self._session_key(ticket_id))
            logger.info("Deleted clarification session for ticket_id=%s", ticket_id)
        except RedisError as exc:
            logger.exception("Failed to delete clarification session for ticket_id=%s", ticket_id)
            raise RuntimeError("Failed to delete clarification session") from exc

    @staticmethod
    def _question_for_field(field: str) -> str:
        return FIELD_QUESTIONS.get(field, f"Уточните поле: {field}.")

    @staticmethod
    def _field_label(field: str) -> str:
        labels = {
            "building": "здание",
            "location": "номер кабинета",
            "problem_description": "описание проблемы",
            "ticket_type": "тип заявки",
            "priority": "срочность",
            "estimated_minutes": "время выполнения",
            "required_skill": "требуемый навык",
            "event_datetime": "дата и время мероприятия",
        }
        return labels.get(field, field)
