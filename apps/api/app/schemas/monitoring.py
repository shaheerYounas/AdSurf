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
    PENDING = "pending"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class RecommendationType(StrEnum):
    KEEP_RUNNING = "keep_running"
    INCREASE_BID = "increase_bid"
    DECREASE_BID = "decrease_bid"
    SET_BID = "set_bid"
    PAUSE_KEYWORD = "pause_keyword"
    PAUSE_TARGET = "pause_target"
    PAUSE_REVIEW = "pause_review"
    ADD_NEGATIVE_EXACT = "add_negative_exact"
    ADD_NEGATIVE_PHRASE = "add_negative_phrase"
    HARVEST_TO_EXACT = "harvest_search_term_to_exact"
    HARVEST_TO_PHRASE = "harvest_search_term_to_phrase"
    MOVE_TO_EXACT = "move_to_exact"
    WATCH_LOCK = "watch_lock"
    WATCH_ONLY = "watch_only"
    NO_ACTION_LOW_DATA = "no_action_low_data"
    DATA_QUALITY_WARNING = "data_quality_warning"
    DATA_QUALITY_REVIEW = "data_quality_review"
    BUDGET_REVIEW = "budget_review"
    INCREASE_CAMPAIGN_BUDGET = "increase_campaign_budget"
    DECREASE_CAMPAIGN_BUDGET = "decrease_campaign_budget"
    MOVE_BUDGET_TO_PROFITABLE = "move_budget_to_profitable_campaign"
    SPLIT_CAMPAIGN = "split_campaign"
    CREATE_EXACT_CAMPAIGN = "create_exact_campaign"
    CREATE_PRODUCT_TARGETING_CAMPAIGN = "create_product_targeting_campaign"
    LEGACY_NEGATIVE_KEYWORD_REVIEW = "negative_keyword_review"


class RecommendationPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecommendationRiskLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class RecommendationSource(StrEnum):
    DETERMINISTIC_RULES = "deterministic_rules"
    AI_REASONING = "ai_reasoning"
    HYBRID = "hybrid"
    UPLOAD_LEARNING = "upload_learning"


class EvidenceQuality(StrEnum):
    STRONG = "strong"
    ADEQUATE = "adequate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"

class RecommendationConfidence(StrEnum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"
    INSUFFICIENT_DATA = "insufficient_data"


class RecommendationEntityType(StrEnum):
    ACCOUNT = "account"
    PRODUCT = "product"
    CAMPAIGN = "campaign"
    AD_GROUP = "ad_group"
    TARGET = "target"
    SEARCH_TERM = "search_term"


class MonitoringImportCreateRequest(BaseModel):
    upload_id: UUID


class RecommendationDecisionRequest(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


class RecommendationBulkDeleteRequest(BaseModel):
    recommendation_ids: list[UUID] = Field(min_length=1, max_length=1000)


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


class EvidenceScore(BaseModel):
    quality: EvidenceQuality = EvidenceQuality.ADEQUATE
    clicks_score: float = Field(default=0.0, ge=0.0, le=1.0)
    spend_score: float = Field(default=0.0, ge=0.0, le=1.0)
    orders_score: float = Field(default=0.0, ge=0.0, le=1.0)
    days_score: float = Field(default=0.0, ge=0.0, le=1.0)
    conversion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    sample_size_adequate: bool = False
    sufficient_history: bool = False

    model_config = ConfigDict(from_attributes=True)


class ExpectedImpact(BaseModel):
    direction: str = "unknown"
    estimated_spend_change_pct: float | None = Field(default=None, ge=-100.0, le=1000.0)
    estimated_sales_change_pct: float | None = Field(default=None, ge=-100.0, le=1000.0)
    estimated_acos_change_pct: float | None = Field(default=None, ge=-100.0, le=1000.0)
    estimated_monthly_impact_usd: float | None = None
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    simulation_method: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Recommendation(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID | None = None
    monitoring_import_id: UUID | None = None
    snapshot_id: UUID | None = None
    account_import_id: UUID | None = None
    entity_key: str | None = None
    decision_source: str | None = None
    agent_run_id: UUID | None = None
    ai_run_id: UUID | None = None
    approval_boundary: dict = Field(default_factory=lambda: {"requires_human_approval": True, "executes_live_amazon_change": False})
    recommendation_type: RecommendationType
    entity_type: RecommendationEntityType = RecommendationEntityType.SEARCH_TERM
    status: RecommendationStatus
    priority: RecommendationPriority
    confidence: RecommendationConfidence = RecommendationConfidence.MEDIUM
    risk_level: RecommendationRiskLevel | None = None
    source: RecommendationSource | None = None
    evidence_score: EvidenceScore | None = None
    expected_impact: ExpectedImpact | None = None
    rule_version_id: str
    rule_name: str
    campaign_name: str | None = None
    ad_group_name: str | None = None
    targeting: str | None = None
    customer_search_term: str | None = None
    match_type: str | None = None
    current_bid: Decimal | None = None
    recommended_bid: Decimal | None = None
    change_percent: Decimal | None = None
    current_budget: Decimal | None = None
    recommended_budget: Decimal | None = None
    input_metrics_json: dict
    current_metric_snapshot_json: dict = Field(default_factory=dict)
    evidence_json: dict = Field(default_factory=dict)
    proposed_action_json: dict
    explanation_json: dict
    bulk_export_status: str | None = None
    learning_feedback_id: UUID | None = None
    previous_recommendation_id: UUID | None = None
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
    product_id: UUID | None = None
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
    job_id: UUID | None = None
    already_imported: bool = False
    message: str | None = None


class MonitoringSummary(BaseModel):
    imports: list[MonitoringImport]
    recommendation_counts: dict[str, int]
    top_recommendations: list[Recommendation]
    agent_summary: dict | None = None
    summary_metrics: dict = Field(default_factory=dict)
    action_recommendation_counts: dict[str, int] = Field(default_factory=dict)
    non_action_insight_counts: dict[str, int] = Field(default_factory=dict)
    issue_counts: dict[str, int] = Field(default_factory=dict)
    detected_product_groups: list[dict] = Field(default_factory=list)
