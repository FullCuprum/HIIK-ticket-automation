from functools import lru_cache

from redis.asyncio import Redis

from app.config import get_settings

settings = get_settings()


@lru_cache
def get_redis() -> Redis:
    """Возвращает singleton async Redis-клиент."""
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_clarification_service() -> "ClarificationService":
    """Dependency factory для ClarificationService."""
    from app.services.clarification import ClarificationService

    return ClarificationService(get_redis())
