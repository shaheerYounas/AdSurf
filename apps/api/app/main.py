from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from apps.api.app.api.routes import api_router
from apps.api.app.core.config import get_settings
from apps.api.app.core.errors import register_error_handlers
from apps.api.app.core.logging_setup import setup_logging
from apps.api.app.core.performance import add_performance_headers_middleware
from apps.api.app.core.sqlite_init import initialize_sqlite_schema
from apps.api.app.schemas.envelope import success_response


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    if settings.database_url and settings.database_url.startswith("sqlite"):
        initialize_sqlite_schema()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
    )
    # Performance: GZip compression for all responses
    app.add_middleware(GZipMiddleware, minimum_size=500)
    # Performance: timing headers and cache control
    app.add_middleware(add_performance_headers_middleware())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "x-user-id", "x-test-workspaces"],
    )
    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/health")
    def health() -> dict:
        return success_response(
            data={
                "status": "ok",
                "service": "api",
                "version": settings.app_version,
            }
        )

    return app


app = create_app()
