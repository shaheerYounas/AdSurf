from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def error_response(code: str, message: str, details: dict | None = None) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(code=exc.code, message=exc.message, details=exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_response(
                code="VALIDATION_ERROR",
                message="Request validation failed.",
                details={"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @app.exception_handler(OperationalError)
    async def handle_database_operational_error(_: Request, exc: OperationalError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_response(
                code="DATABASE_UNREACHABLE",
                message=(
                    "Database could not be reached. For Supabase local development, use the IPv4-compatible "
                    "Supabase pooler connection string in DATABASE_URL when the direct db.<project>.supabase.co host is unavailable."
                ),
                details={"reason": str(getattr(exc, "orig", exc))[:500]},
            ),
        )
