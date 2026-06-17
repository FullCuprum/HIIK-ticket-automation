from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.utils.password import hash_password

DEMO_USERS = [
    {
        "username": "admin",
        "password": "admin",
        "role": "admin",
        "must_change_password": False,
    },
    {
        "username": "employee",
        "password": "employee",
        "role": "employee",
        "must_change_password": False,
    },
    {
        "username": "user",
        "password": "user",
        "role": "user",
        "must_change_password": False,
    },
]


async def ensure_demo_users(db: AsyncSession) -> None:
    """Создаёт демо-пользователей, если их ещё нет в базе."""
    for demo_user in DEMO_USERS:
        result = await db.execute(select(User).where(User.username == demo_user["username"]))
        existing = result.scalar_one_or_none()
        if existing is not None:
            if existing.role == "manager":
                existing.role = "admin"
            continue

        db.add(
            User(
                username=demo_user["username"],
                password_hash=hash_password(demo_user["password"]),
                role=demo_user["role"],
                must_change_password=demo_user["must_change_password"],
                is_active=True,
            )
        )

    await db.flush()
