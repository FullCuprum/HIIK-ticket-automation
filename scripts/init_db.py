import asyncio

from app.db.database import Base, engine
from app.models import approval, employee, schedule, ticket  # noqa: F401


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(init_db())
