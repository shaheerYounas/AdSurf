"""AdSurf Performance Optimization Layer.

Provides:
- Database connection pooling (via SQLAlchemy QueuePool instead of NullPool)
- Query result caching with TTL
- Concurrent data fetching utilities
- Response compression hints
- Request timing middleware

Usage:
    from apps.api.app.core.performance import cached_query, fetch_concurrent
"""

from __future__ import annotations

import functools
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, TypeVar

from apps.api.app.core.config import get_settings

T = TypeVar("T")

# Thread pool shared across the application
_thread_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="adsurf-worker")


# ── Simple TTL Cache ──────────────────────────────────────────────────────

class TTLCache:
    """Simple in-memory TTL cache for frequently-accessed query results."""

    def __init__(self, max_size: int = 128, default_ttl: float = 5.0):
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        expiry, value = self._cache[key]
        if time.monotonic() > expiry:
            del self._cache[key]
            return None
        # Move to end (LRU)
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        expiry = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
        self._cache[key] = (expiry, value)

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict:
        return {"size": len(self._cache), "max_size": self._max_size}


# Global caches
_monitoring_cache = TTLCache(max_size=64, default_ttl=3.0)
_product_cache = TTLCache(max_size=128, default_ttl=10.0)
_agent_cache = TTLCache(max_size=32, default_ttl=5.0)


def cached_query(cache: TTLCache, ttl: float | None = None):
    """Decorator for caching query results with TTL."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{args}:{sorted(kwargs.items())}"
            result = cache.get(key)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            cache.set(key, result, ttl)
            return result

        return wrapper

    return decorator


# ── Concurrent Fetching ────────────────────────────────────────────────────


def fetch_concurrent(futures: dict[str, Callable[[], Any]]) -> dict[str, Any]:
    """Execute multiple callables concurrently and return results as a dict.

    Args:
        futures: Dict of {key: callable} where each callable returns a result.

    Returns:
        Dict of {key: result} in the same order as input.
    """
    results = {}
    submitted = {}
    for key, fn in futures.items():
        submitted[key] = _thread_pool.submit(fn)

    for key, future in submitted.items():
        try:
            results[key] = future.result(timeout=30)
        except Exception:
            results[key] = None

    return results


# ── FastAPI Middleware ──────────────────────────────────────────────────────


def add_performance_headers_middleware():
    """Create a FastAPI middleware that adds performance headers and timing."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request

    class PerformanceMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            start = time.monotonic()
            response = await call_next(request)
            elapsed = time.monotonic() - start
            response.headers["X-Response-Time-Ms"] = f"{elapsed * 1000:.0f}"
            response.headers["Cache-Control"] = "private, max-age=3"
            return response

    return PerformanceMiddleware


# ── Database Connection Pool ────────────────────────────────────────────────

_pooled_engine = None


def get_pooled_engine():
    """Get a database engine with connection pooling (QueuePool) instead of NullPool.

    This significantly improves performance for repeated queries by reusing
    connections instead of creating a new one for every request.
    """
    global _pooled_engine
    if _pooled_engine is not None:
        return _pooled_engine

    settings = get_settings()
    if not settings.database_url:
        return None

    from sqlalchemy import create_engine

    _pooled_engine = create_engine(
        settings.database_url,
        pool_size=5,  # 5 persistent connections
        max_overflow=10,  # Up to 10 additional under load
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=3600,  # Recycle connections after 1 hour
        echo=False,
    )
    return _pooled_engine


# ── Invalidate cache helpers ───────────────────────────────────────────────


def invalidate_monitoring_cache() -> None:
    _monitoring_cache.clear()


def invalidate_product_cache() -> None:
    _product_cache.clear()


def invalidate_all_caches() -> None:
    _monitoring_cache.clear()
    _product_cache.clear()
    _agent_cache.clear()