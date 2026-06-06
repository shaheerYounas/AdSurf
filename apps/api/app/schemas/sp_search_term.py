"""Pydantic schemas for SP Search Term pipeline API responses."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SPImportHealthResponse(BaseModel):
    """Full import health payload returned by GET /uploads/{id}/import-health."""

    upload_id: UUID
    parse_run_id: UUID | None = None
    report_type: str
    total_rows: int
    valid_rows: int
    warning_rows: int
    error_rows: int
    quarantined_rows: int
    missing_columns: list[str]
    unknown_columns: list[str]
    date_range_start: date | None = None
    date_range_end: date | None = None
    currency: str | None = None
    marketplace: str | None = None
    schema_valid: bool
    can_generate_recommendations: bool
    top_issues: list[dict]
    aggregated_rows: list[dict] = []

    model_config = ConfigDict(from_attributes=True)
