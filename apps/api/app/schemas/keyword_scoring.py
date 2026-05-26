from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class KeywordScoringRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class KeywordCandidateStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


class KeywordScoringRun(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    upload_id: UUID
    parse_run_id: UUID
    column_mapping_id: UUID
    status: KeywordScoringRunStatus
    scoring_version: int
    rule_version_id: UUID | None = None
    idempotency_key: str
    total_rows: int
    scored_rows: int
    approved_count: int
    rejected_count: int
    error_count: int
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class KeywordCandidate(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    upload_id: UUID
    parse_run_id: UUID
    column_mapping_id: UUID
    scoring_run_id: UUID
    source_row_id: UUID
    search_term: str | None = None
    search_volume: Decimal | None = None
    competitor_rank_values_json: list[dict]
    relevance_score: int | None = None
    scoring_status: KeywordCandidateStatus
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KeywordScoringSummary(BaseModel):
    scoring_run_id: UUID
    status: KeywordScoringRunStatus
    total_rows: int
    scored_rows: int
    approved_count: int
    rejected_count: int
    error_count: int
