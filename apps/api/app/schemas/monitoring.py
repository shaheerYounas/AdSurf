from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MonitoringImportStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RecommendationStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class RecommendationType(StrEnum):
    INCREASE_BID = "increase_bid"
    DECREASE_BID = "decrease_bid"
    PAUSE_REVIEW = "pause_review"
    NEGATIVE_KEYWORD_REVIEW = "negative_keyword_review"
    WATCH_LOCK = "watch_lock"


class RecommendationPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MonitoringImportCreateRequest(BaseModel):
    upload_id: UUID


class RecommendationDecisionRequest(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


class MonitoringImport(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    upload_id: UUID
    parse_run_id: UUID
    report_type: str
    status: MonitoringImportStatus
    date_range_start: str | None = None
    date_range_end: str | None = None
    total_rows: int = 0
    processed_rows: int = 0
    error_rows: int = 0
    data_quality_warnings_json: list[dict] = Field(default_factory=list)
    created_by: str
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MonitoringSnapshot(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    monitoring_import_id: UUID
    upload_id: UUID
    parse_run_id: UUID
    source_row_id: UUID
    campaign_name: str
    ad_group_name: str
    targeting: str
    match_type: str | None = None
    customer_search_term: str
    start_date: str | None = None
    end_date: str | None = None
    impressions: int
    clicks: int
    spend: Decimal
    sales: Decimal
    orders: int
    units: int | None = None
    cpc: Decimal | None = None
    ctr: Decimal | None = None
    cvr: Decimal | None = None
    acos: Decimal | None = None
    roas: Decimal | None = None
    raw_metrics_json: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Recommendation(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    monitoring_import_id: UUID
    snapshot_id: UUID
    recommendation_type: RecommendationType
    status: RecommendationStatus
    priority: RecommendationPriority
    rule_version_id: str
    rule_name: str
    campaign_name: str
    ad_group_name: str
    targeting: str
    customer_search_term: str
    input_metrics_json: dict
    proposed_action_json: dict
    explanation_json: dict
    decided_by: str | None = None
    decision_note: str | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecommendationDecision(BaseModel):
    id: UUID
    workspace_id: UUID
    recommendation_id: UUID
    decision: RecommendationStatus
    actor_user_id: str
    note: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AiRun(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_name: str
    provider: str
    model: str
    schema_version: str
    input_hash: str
    output_json: dict
    status: str
    latency_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MonitoringImportResponse(BaseModel):
    import_record: MonitoringImport
    job_id: UUID


class MonitoringSummary(BaseModel):
    imports: list[MonitoringImport]
    recommendation_counts: dict[str, int]
    top_recommendations: list[Recommendation]
    agent_summary: dict | None = None
