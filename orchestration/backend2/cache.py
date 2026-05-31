"""Redis Caching Layer - High-performance caching with TTL support"""

from __future__ import annotations

import json
import time
from functools import wraps
from typing import Any, Callable, Optional

from redis import Redis
from redis.exceptions import RedisError

from backend2.config import CACHE_PATTERNS, REDIS_URL
from backend2.logging_utils import get_logger

logger = get_logger(__name__)

# Pre-configured cache key patterns for specific endpoints
CACHE_KEYS = {
    "company_list": "company_list:all",
    "company_detail": "company_detail:{company_id}",
    "financial_trend": "financial_trend:{company_id}:{year}",
    "sector_list": "sector_list:all",
    "health_scores": "health_scores:all",
    "health_score": "health_score:{company_id}",
    "sector_companies": "sector_companies:{sector_id}",
    "peer_comparison": "peer_comparison:{company_id}",
    "dashboard_summary": "dashboard_summary:all",
    "annual_report": "annual_report:{company_id}:{year}",
}


def get_redis_client() -> Redis:
    """Get Redis client connection"""
    return Redis.from_url(REDIS_URL, decode_responses=True)


def invalidate_cache(patterns: list[str] | None = None) -> dict[str, int | list[str]]:
    """
    Invalidate cache by pattern matching.
    
    Args:
        patterns: List of glob patterns to invalidate (uses CACHE_PATTERNS if None)
    
    Returns:
        Summary of deleted keys
    """
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
        extra={"event": "cache_invalidation", "extra_data": summary},
    )
    return summary


def ping_redis() -> dict[str, str | bool]:
    """Test Redis connectivity"""
    try:
        ok = bool(get_redis_client().ping())
        return {"redis_up": ok, "redis_url": REDIS_URL}
    except RedisError as exc:
        logger.exception("Redis ping failed")
        return {"redis_up": False, "redis_url": REDIS_URL, "error": str(exc)}


def cache_get(key: str) -> Optional[Any]:
    """
    Retrieve value from Redis cache.
    
    Args:
        key: Cache key
    
    Returns:
        Cached value (deserialized JSON) or None if not found
    """
    try:
        redis_client = get_redis_client()
        value = redis_client.get(key)
        if value:
            return json.loads(value)
        return None
    except RedisError as e:
        logger.warning(f"Cache GET failed for key '{key}': {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Cache value deserialization failed for key '{key}': {str(e)}")
        return None


def cache_set(key: str, value: Any, ttl_seconds: int = 3600) -> bool:
    """
    Store value in Redis cache with optional TTL.
    
    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl_seconds: Time-to-live in seconds (default: 1 hour)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        redis_client = get_redis_client()
        serialized = json.dumps(value)
        redis_client.setex(key, ttl_seconds, serialized)
        return True
    except RedisError as e:
        logger.warning(f"Cache SET failed for key '{key}': {str(e)}")
        return False
    except json.JSONEncodeError as e:
        logger.warning(f"Cache value serialization failed for key '{key}': {str(e)}")
        return False


def cache_delete(key: str) -> bool:
    """
    Delete a key from Redis cache.
    
    Args:
        key: Cache key
    
    Returns:
        True if key was deleted, False if not found or error
    """
    try:
        redis_client = get_redis_client()
        return bool(redis_client.delete(key))
    except RedisError as e:
        logger.warning(f"Cache DELETE failed for key '{key}': {str(e)}")
        return False


def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern from Redis cache.
    
    Args:
        pattern: Redis glob pattern (e.g., 'company_profile:*')
    
    Returns:
        Number of keys deleted
    """
    try:
        redis_client = get_redis_client()
        keys = list(redis_client.scan_iter(match=pattern, count=1000))
        if keys:
            return redis_client.delete(*keys)
        return 0
    except RedisError as e:
        logger.warning(f"Cache DELETE PATTERN failed for pattern '{pattern}': {str(e)}")
        return 0


def cached_endpoint(ttl_seconds: int = 3600, key_prefix: str = "endpoint"):
    """
    Decorator for caching API endpoint responses.
    
    Args:
        ttl_seconds: Cache TTL in seconds
        key_prefix: Prefix for cache keys
    
    Usage:
        @cached_endpoint(ttl_seconds=1800, key_prefix="company_detail")
        def get_company_detail(company_id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Build cache key from function name and arguments
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get from cache
            cached_value = cache_get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached_value
            
            # Call original function
            result = func(*args, **kwargs)
            
            # Store in cache
            cache_set(cache_key, result, ttl_seconds)
            logger.debug(f"Cache MISS and SET: {cache_key}")
            
            return result
        
        return wrapper
    
    return decorator
