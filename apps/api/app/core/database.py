from functools import lru_cache

from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from apps.api.app.core.config import get_settings
from apps.api.app.core.errors import ApiError


@lru_cache
def get_database_engine() -> Engine:
    settings = get_settings()
    if not settings.database_url:
        raise ApiError(
            code="DATABASE_NOT_CONFIGURED",
            message="DATABASE_URL is required for database-backed operations.",
            status_code=503,
        )
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args={"connect_timeout": 10},
    )


def run_database_operation(operation):
    try:
        return operation()
    except OperationalError as exc:
        raise ApiError(
            code="DATABASE_UNREACHABLE",
            message=(
                "Database could not be reached. For Supabase local development, use the IPv4-compatible "
                "Supabase pooler connection string in DATABASE_URL when the direct db.<project>.supabase.co host is unavailable."
            ),
            status_code=503,
            details={"reason": str(exc.orig)[:500]},
        ) from exc


def assert_database_configured_for_environment() -> None:
    settings = get_settings()
    if not settings.database_url and not settings.is_local_or_test:
        raise ApiError(
            code="DATABASE_NOT_CONFIGURED",
            message="DATABASE_URL must be configured outside local and test environments.",
            status_code=503,
        )
