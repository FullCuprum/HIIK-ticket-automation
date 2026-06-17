import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

TRANSLIT_MAP = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate(value: str) -> str:
    result: list[str] = []
    for char in value.lower():
        if char in TRANSLIT_MAP:
            result.append(TRANSLIT_MAP[char])
        elif char.isascii() and char.isalnum():
            result.append(char)
        elif char in {" ", "-", "."}:
            result.append("_")
    return "".join(result)


def username_base_from_full_name(full_name: str) -> str:
    parts = [part for part in transliterate(full_name).split("_") if part]
    if not parts:
        return "employee"
    if len(parts) == 1:
        return parts[0][:40]
    return f"{parts[0]}_{parts[1][0]}"[:40]


async def generate_unique_username(db: AsyncSession, full_name: str) -> str:
    base = username_base_from_full_name(full_name)
    base = re.sub(r"_+", "_", base).strip("_") or "employee"
    candidate = base
    suffix = 1

    while True:
        result = await db.execute(select(User.id).where(User.username == candidate).limit(1))
        if result.scalar_one_or_none() is None:
            return candidate
        suffix += 1
        candidate = f"{base}_{suffix}"
