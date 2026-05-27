from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.api.routes import api_router
from apps.api.app.core.config import get_settings
from apps.api.app.core.errors import register_error_handlers
from apps.api.app.core.logging_setup import setup_logging
from apps.api.app.schemas.envelope import success_response


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
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
