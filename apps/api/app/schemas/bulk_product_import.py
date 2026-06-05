"""Pydantic schemas for bulk product profile import."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BulkImportStatus(StrEnum):
    PARSING = "parsing"
    VALIDATING = "validating"
    READY_FOR_REVIEW = "ready_for_review"
    CREATING = "creating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BulkImportRowStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    DUPLICATE_IN_FILE = "duplicate_in_file"
    ALREADY_EXISTS = "already_exists"
    SKIPPED = "skipped"
    CREATED = "created"
    UPDATED = "updated"
    FAILED = "failed"


class BulkImportConflictStrategy(StrEnum):
    SKIP_EXISTING = "skip_existing"
    UPDATE_EXISTING = "update_existing"
    CREATE_ONLY_MISSING = "create_only_missing"


class BulkProductRowValidationError(BaseModel):
    field: str
    message: str
    raw_value: str | None = None


class BulkProductRow(BaseModel):
    """One parsed + validated row from the bulk import file."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    row_number: int
    status: BulkImportRowStatus

    # Mapped fields
    product_name: str | None = None
    asin: str | None = None
    sku: str | None = None
    marketplace: str | None = None
    currency: str | None = None
    target_acos: Decimal | None = None
    default_budget: Decimal | None = None
    default_bid: Decimal | None = None
    brand: str | None = None
    category: str | None = None
    notes: str | None = None

    # Outcome
    product_id: UUID | None = None
    validation_errors: list[BulkProductRowValidationError] = Field(default_factory=list)
    raw_row_json: dict[str, Any] = Field(default_factory=dict)


class BulkProductImport(BaseModel):
    """Full import record with summary counts."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    upload_id: UUID | None = None
    original_filename: str
    file_hash: str | None = None
    status: BulkImportStatus
    conflict_strategy: BulkImportConflictStrategy

    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_in_file_rows: int
    already_exists_rows: int
    created_rows: int
    updated_rows: int = 0
    skipped_rows: int
    failed_rows: int

    detected_columns_json: dict[str, str] = Field(default_factory=dict)

    workspace_default_acos: Decimal | None = None
    workspace_default_budget: Decimal | None = None
    workspace_default_bid: Decimal | None = None

    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class BulkProductImportWithRows(BulkProductImport):
    """Import record with all rows for the review step."""

    rows: list[BulkProductRow] = Field(default_factory=list)


# ─── Request / response bodies ────────────────────────────────────────────────


class BulkProductImportCreateRequest(BaseModel):
    """Kick off a bulk import from an already-uploaded file (upload_id + filename)."""

    upload_id: UUID | None = None
    original_filename: str = Field(min_length=1, max_length=500)
    conflict_strategy: BulkImportConflictStrategy = BulkImportConflictStrategy.SKIP_EXISTING

    # Workspace defaults used when a row is missing a required field
    workspace_default_acos: Decimal | None = Field(default=None, gt=Decimal("0"), le=Decimal("1"))
    workspace_default_budget: Decimal | None = Field(default=None, gt=Decimal("0"))
    workspace_default_bid: Decimal | None = Field(default=None, gt=Decimal("0"))


class BulkProductImportCommitRequest(BaseModel):
    """Trigger actual product creation from a READY_FOR_REVIEW import."""

    conflict_strategy: BulkImportConflictStrategy = BulkImportConflictStrategy.SKIP_EXISTING


class BulkProductImportSummary(BaseModel):
    """Lightweight summary for the pre-commit review step."""

    import_id: UUID
    status: BulkImportStatus
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_in_file_rows: int
    already_exists_rows: int
    rows_needing_review: int  # invalid + duplicate_in_file
    exportable_valid_rows: int  # rows that can be auto-created
    rows_to_create: int = 0
    rows_to_update: int = 0
    rows_to_skip: int = 0
    warning_rows: int = 0
    detected_columns: dict[str, str]  # original_col -> mapped_field
    exception_rows: list[BulkProductRow]  # rows that need human review
