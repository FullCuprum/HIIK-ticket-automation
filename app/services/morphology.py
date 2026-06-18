from __future__ import annotations

import re
from functools import lru_cache

from pymorphy2 import MorphAnalyzer

WORD_PATTERN = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)


@lru_cache
def get_morph_analyzer() -> MorphAnalyzer | None:
    try:
        return MorphAnalyzer()
    except Exception:
        return None


def lemmatize_word(word: str, morph: MorphAnalyzer | None = None) -> str:
    analyzer = morph or get_morph_analyzer()
    if analyzer is None:
        return word.lower()

    parsed = analyzer.parse(word.lower())
    if not parsed:
        return word.lower()
    return parsed[0].normal_form


def tokenize_words(text: str) -> list[str]:
    return WORD_PATTERN.findall(text.lower())


def build_lexical_forms(text: str, morph: MorphAnalyzer | None = None) -> set[str]:
    """Возвращает набор слов и их нормальных форм для сопоставления со словарём."""
    analyzer = morph or get_morph_analyzer()
    forms: set[str] = set()

    for token in tokenize_words(text):
        forms.add(token)
        if analyzer is not None:
            forms.add(lemmatize_word(token, analyzer))

    return forms


def contains_keyword(text: str, keyword: str, morph: MorphAnalyzer | None = None) -> bool:
    keyword = keyword.lower().strip()
    if not keyword:
        return False

    lowered_text = text.lower()
    if keyword in lowered_text:
        return True

    parts = [part for part in keyword.split() if part]
    if len(parts) <= 1:
        forms = build_lexical_forms(text, morph)
        if parts and parts[0] in forms:
            return True
        if analyzer := morph or get_morph_analyzer():
            return lemmatize_word(parts[0], analyzer) in forms if parts else False
        return False

    forms = build_lexical_forms(text, morph)
    analyzer = morph or get_morph_analyzer()
    for part in parts:
        part_match = part in forms
        if not part_match and analyzer is not None:
            part_match = lemmatize_word(part, analyzer) in forms
        if not part_match:
            return False
    return True


def count_keyword_hits(text: str, keywords: list[str], morph: MorphAnalyzer | None = None) -> int:
    return sum(1 for keyword in keywords if contains_keyword(text, keyword, morph))
