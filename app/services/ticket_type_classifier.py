from __future__ import annotations

import re

from dataclasses import dataclass

from app.services.entities import EntityExtractionResult
from app.services.morphology import count_keyword_hits, get_morph_analyzer
from app.services.ticket_types import TICKET_TYPES, TYPE_KEYWORD_FIELDS

CONFIDENCE_GAP = 1


@dataclass(frozen=True)
class ClassificationResult:
    ticket_type: str | None
    scores: dict[str, int]
    ambiguous: bool


def _base_scores(text: str, vocabulary: dict[str, list[str]]) -> dict[str, int]:
    morph = get_morph_analyzer()
    scores = {ticket_type: 0 for ticket_type in TICKET_TYPES}

    for ticket_type, field_name in TYPE_KEYWORD_FIELDS.items():
        keywords = vocabulary.get(field_name, [])
        scores[ticket_type] = count_keyword_hits(text, keywords, morph)

    problem_keywords = vocabulary.get("problem_keywords", [])
    scores["repair"] += count_keyword_hits(text, problem_keywords, morph)

    return scores


def apply_negative_rules(text: str, scores: dict[str, int], vocabulary: dict[str, list[str]]) -> dict[str, int]:
    lowered = text.lower()
    adjusted = dict(scores)

    if "мероприят" in lowered:
        adjusted["event_support"] += 3
        if any(token in lowered for token in ("установ", "установк", "инсталл")):
            adjusted["software_installation"] = max(0, adjusted["software_installation"] - 3)
        if any(token in lowered for token in ("проектор", "звук", "микрофон", "колонк", "презентац")):
            adjusted["event_support"] += 2
            adjusted["repair"] = max(0, adjusted["repair"] - 1)

    if "консультац" in lowered or "подскаж" in lowered or "объясн" in lowered:
        adjusted["consultation"] += 3
        adjusted["repair"] = max(0, adjusted["repair"] - 1)

    if "инструктаж" in lowered or "учётн" in lowered or "учетн" in lowered:
        adjusted["consultation"] += 2

    if any(token in lowered for token in ("видеонаблюд", "регистратор", "видеорегистратор")):
        adjusted["video_surveillance"] += 4
        adjusted["repair"] = max(0, adjusted["repair"] - 2)
    elif "камер" in lowered and any(token in lowered for token in ("общежит", "коридор", "вахт")):
        adjusted["video_surveillance"] += 2

    if "вебинар" in lowered or ("защит" in lowered and "диплом" in lowered):
        adjusted["event_support"] += 3

    if "обновить windows" in lowered or "обновление windows" in lowered:
        adjusted["software_installation"] += 3

    if "подготов" in lowered and ("аудитор" in lowered or re.search(r"\bауд\b", lowered)):
        adjusted["workspace_setup"] += 5
        adjusted["repair"] = max(0, adjusted["repair"] - 2)

    if "можно ли" in lowered or lowered.strip().endswith("?"):
        adjusted["consultation"] += 2

    if any(token in lowered for token in ("рабоч", "место", "новый сотрудник", "выход на работу")):
        adjusted["workspace_setup"] += 2

    if "подготов" in lowered and "рабоч" in lowered:
        adjusted["workspace_setup"] += 5
        adjusted["software_installation"] = max(0, adjusted["software_installation"] - 3)

    if any(token in lowered for token in ("перенест", "перевез", "оборудовать", "переговорн")):
        adjusted["workspace_setup"] += 2

    if "день открытых" in lowered or "актов" in lowered:
        adjusted["event_support"] += 2

    negative_rules = vocabulary.get("negative_rules", [])
    for rule in negative_rules:
        if_tokens = rule.get("if_any", [])
        if not any(token in lowered for token in if_tokens):
            continue

        prefer = rule.get("prefer")
        penalize = rule.get("penalize")
        boost = int(rule.get("boost", 2))
        penalty = int(rule.get("penalty", 2))

        if prefer:
            adjusted[prefer] = adjusted.get(prefer, 0) + boost
        if penalize:
            adjusted[penalize] = max(0, adjusted.get(penalize, 0) - penalty)

    return adjusted


def classify_ticket_type(
    raw_text: str,
    cleaned_text: str,
    entities: EntityExtractionResult,
    vocabulary: dict[str, list[str]],
) -> ClassificationResult:
    combined_text = f"{raw_text} {cleaned_text}".strip()
    scores = _base_scores(combined_text, vocabulary)

    if entities.software_mentions:
        scores["software_installation"] += len(entities.software_mentions) + 1

    scores = apply_negative_rules(combined_text, scores, vocabulary)

    if "подготов" in combined_text.lower() and "рабоч" in combined_text.lower():
        scores["software_installation"] = min(scores["software_installation"], 2)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_type, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    if best_score <= 0:
        return ClassificationResult(ticket_type="other", scores=scores, ambiguous=False)

    ambiguous = best_score == second_score or (best_score - second_score) < CONFIDENCE_GAP
    if ambiguous:
        return ClassificationResult(ticket_type=None, scores=scores, ambiguous=True)

    return ClassificationResult(ticket_type=best_type, scores=scores, ambiguous=False)
