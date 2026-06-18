"""Запуск сидирования демонстрационных данных."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import AsyncSessionLocal
from app.services.demo_seed import DEMO_PASSWORD, DEMO_USERS, ensure_demo_dataset


async def main() -> int:
    async with AsyncSessionLocal() as session:
        created = await ensure_demo_dataset(session)
        await session.commit()

    if created:
        print("Демонстрационные данные добавлены.")
        print(f"Дополнительные пользователи (пароль: {DEMO_PASSWORD}):")
        for user in DEMO_USERS:
            print(f"  - {user['username']} ({user['role']}): {user['full_name']}")
        return 0

    print("Демонстрационные данные уже присутствуют в базе.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
