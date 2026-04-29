from __future__ import annotations

from redis import Redis
from redis.exceptions import RedisError

from backend2.config import CACHE_PATTERNS, REDIS_URL
from backend2.logging_utils import get_logger

logger = get_logger(__name__)


def get_redis_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def invalidate_cache(patterns: list[str] | None = None) -> dict[str, int | list[str]]:
    selected_patterns = patterns or CACHE_PATTERNS
    redis_client = get_redis_client()

    summary = {
        "deleted_keys": 0,
        "patterns": selected_patterns,
    }

    for pattern in selected_patterns:
        keys = list(redis_client.scan_iter(match=pattern, count=1000))
        if not keys:
            continue
        summary["deleted_keys"] += redis_client.delete(*keys)

    logger.info(
        "Cache invalidation completed",
        extra={
            "event": "cache_invalidation",
            "extra_data": summary,
        },
    )
    return summary


def ping_redis() -> dict[str, str | bool]:
    try:
        ok = bool(get_redis_client().ping())
        return {"redis_up": ok, "redis_url": REDIS_URL}
    except RedisError as exc:
        logger.exception("Redis ping failed")
        return {"redis_up": False, "redis_url": REDIS_URL, "error": str(exc)}
