from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompetitorUploadStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CompetitorUpload(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID | None = None
    original_filename: str
    storage_path: str
    mime_type: str
    file_size_bytes: int
    status: CompetitorUploadStatus
    row_count: int = 0
    cleaned_column_count: int = 0
    detected_columns_json: list[dict] = []
    warnings_json: list[dict] = []
    error_message: str | None = None
    uploaded_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompetitorCleanedRow(BaseModel):
    id: UUID
    workspace_id: UUID
    competitor_upload_id: UUID
    row_number: int
    search_term: str | None = None
    search_volume: float | None = None
    competitor_rank_values_json: list[dict] = []
    raw_metrics_json: dict | None = None
    relevance_score: int | None = None
    scoring_status: str | None = None
    rejection_reason: str | None = None
    scored_at: datetime | None = None
    verification_status: str | None = None
    verification_result_json: dict | None = None
    verified_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompetitorVerificationResponse(BaseModel):
    upload: CompetitorUpload | None = None
    verified_count: int
    unverified_count: int
    total_count: int
    preview_rows: list[CompetitorCleanedRow] = []


class CampaignGenerationResponse(BaseModel):
    upload: CompetitorUpload
    campaign_count: int
    hero_campaign_name: str
    group_count: int
    bulk_export_preview: list[dict] = []


class CompetitorScoringResponse(BaseModel):
    upload: CompetitorUpload
    total_rows: int
    scored_rows: int
    approved_count: int
    rejected_count: int
    error_count: int
    preview_rows: list[CompetitorCleanedRow] = []


class CompetitorUploadResponse(BaseModel):
    upload: CompetitorUpload
    cleaned_rows: list[CompetitorCleanedRow] = []
    total_rows: int = 0
    warnings: list[dict] = []


class CompetitorUploadListResponse(BaseModel):
    uploads: list[CompetitorUpload]
    total: int


class CompetitorCleanedRowsResponse(BaseModel):
    rows: list[CompetitorCleanedRow]
    upload: CompetitorUpload
    total: int
    page: int
    page_size: int
    has_next: bool


class CompetitorReference(BaseModel):
    name: str
    asin: str | None = None


class CompetitorVerificationEvidenceResult(BaseModel):
    position: int = Field(ge=1)
    title: str | None = None
    asin: str | None = None
    matched_competitor_name: str | None = None
    matched_competitor_asin: str | None = None


class CompetitorVerificationEvidenceRow(BaseModel):
    search_term: str
    results: list[CompetitorVerificationEvidenceResult] = []


class CompetitorVerificationRequest(BaseModel):
    competitors: list[str | CompetitorReference]
    evidence_rows: list[CompetitorVerificationEvidenceRow] = []
    required_match_count: int = Field(default=3, ge=3, le=5)
