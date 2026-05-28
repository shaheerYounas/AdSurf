from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_FOR_DEPENDENCY = "waiting_for_dependency"
    WAITING_FOR_USER = "waiting_for_user"


class AgentMode(StrEnum):
    DETERMINISTIC = "deterministic"
    AI = "ai"
    HYBRID = "hybrid"


class AgentStrictnessLevel(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class AgentConfidenceThreshold(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentProvider(StrEnum):
    PRIMARY = "primary"
    DEEPSEEK = "deepseek"
    FALLBACK = "fallback"
    DETERMINISTIC = "deterministic"


class AgentAnalysisDepth(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class AgentOptimizationGoal(StrEnum):
    REDUCE_WASTED_SPEND = "reduce_wasted_spend"
    INCREASE_SALES = "increase_sales"
    IMPROVE_ROAS = "improve_roas"
    LAUNCH_NEW_PRODUCTS = "launch_new_products"
    SCALE_WINNERS = "scale_winners"
    CONSERVATIVE_PROFITABILITY = "conservative_profitability"


class AgentExplanationDetail(StrEnum):
    SIMPLE = "simple"
    NORMAL = "normal"
    EXPERT = "expert"


class AgentChunkStrategy(StrEnum):
    BY_PRODUCT = "by_product"
    BY_CAMPAIGN = "by_campaign"
    BY_ENTITY_PRIORITY = "by_entity_priority"


class AgentDefinition(BaseModel):
    agent_id: str
    display_name: str
    description: str
    task_type: str
    enabled_by_default: bool = True
    allowed_actions: list[str]
    input_dependencies: list[str] = Field(default_factory=list)
    output_type: str
    can_be_disabled: bool = True
    can_be_rerun: bool = True
    can_be_stopped: bool = True
    requires_human_approval: bool = True
    can_mutate_live_amazon_ads: bool = False


class AgentConfig(BaseModel):
    workspace_id: UUID
    product_id: UUID | None = None
    agent_id: str
    enabled: bool = True
    mode: AgentMode = AgentMode.HYBRID
    provider: AgentProvider = AgentProvider.DEEPSEEK
    model: str | None = None
    strictness_level: AgentStrictnessLevel = AgentStrictnessLevel.BALANCED
    confidence_threshold: AgentConfidenceThreshold = AgentConfidenceThreshold.MEDIUM
    max_recommendations: int = Field(default=100, ge=1, le=1000)
    max_rows_per_ai_call: int = Field(default=500, ge=1, le=50000)
    max_groups_per_ai_call: int = Field(default=100, ge=1, le=5000)
    max_products_per_run: int = Field(default=50, ge=1, le=10000)
    analysis_depth: AgentAnalysisDepth = AgentAnalysisDepth.STANDARD
    include_account_level_analysis: bool = True
    include_product_level_analysis: bool = True
    include_campaign_level_analysis: bool = True
    include_keyword_level_analysis: bool = True
    include_search_term_level_analysis: bool = True
    allow_bid_recommendations: bool = True
    allow_negative_keyword_recommendations: bool = True
    allow_pause_recommendations: bool = True
    allow_budget_recommendations: bool = True
    allow_keep_running: bool = True
    allow_increase_bid: bool = True
    allow_decrease_bid: bool = True
    allow_pause_review: bool = True
    allow_negative_exact: bool = True
    allow_negative_phrase: bool = True
    allow_move_to_exact: bool = True
    allow_budget_review: bool = True
    allow_data_quality_review: bool = True
    allow_product_mapping_recommendations: bool = True
    max_bid_increase_multiplier: Decimal = Field(default=Decimal("1.1000"), ge=Decimal("1.0000"), le=Decimal("3.0000"))
    max_bid_decrease_multiplier: Decimal = Field(default=Decimal("0.9000"), ge=Decimal("0.1000"), le=Decimal("1.0000"))
    require_high_confidence_for_pause: bool = True
    require_high_confidence_for_negative_keywords: bool = True
    require_min_clicks_before_action: int = Field(default=10, ge=0)
    require_min_spend_before_action: Decimal = Field(default=Decimal("10.0000"), ge=Decimal("0"))
    target_acos_override: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("10"))
    min_orders_for_scaling: int = Field(default=2, ge=0)
    min_roas_for_scaling: Decimal = Field(default=Decimal("2.0000"), ge=Decimal("0"))
    custom_system_instruction: str | None = Field(default=None, max_length=4000)
    custom_business_goal: str | None = Field(default=None, max_length=2000)
    optimization_goal: AgentOptimizationGoal = AgentOptimizationGoal.CONSERVATIVE_PROFITABILITY
    brand_safety_notes: str | None = Field(default=None, max_length=2000)
    competitor_notes: str | None = Field(default=None, max_length=2000)
    product_margin_notes: str | None = Field(default=None, max_length=2000)
    recommendation_language: str = Field(default="en", min_length=2, max_length=20)
    explanation_detail: AgentExplanationDetail = AgentExplanationDetail.NORMAL
    show_raw_ai_reasoning_summary: bool = False
    show_metric_evidence: bool = True
    require_action_risk_note: bool = True
    chunk_strategy: AgentChunkStrategy = AgentChunkStrategy.BY_PRODUCT
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentConfigPatch(BaseModel):
    product_id: UUID | None = None
    enabled: bool | None = None
    mode: AgentMode | None = None
    provider: AgentProvider | None = None
    model: str | None = Field(default=None, max_length=200)
    strictness_level: AgentStrictnessLevel | None = None
    confidence_threshold: AgentConfidenceThreshold | None = None
    max_recommendations: int | None = Field(default=None, ge=1, le=1000)
    max_rows_per_ai_call: int | None = Field(default=None, ge=1, le=50000)
    max_groups_per_ai_call: int | None = Field(default=None, ge=1, le=5000)
    max_products_per_run: int | None = Field(default=None, ge=1, le=10000)
    analysis_depth: AgentAnalysisDepth | None = None
    include_account_level_analysis: bool | None = None
    include_product_level_analysis: bool | None = None
    include_campaign_level_analysis: bool | None = None
    include_keyword_level_analysis: bool | None = None
    include_search_term_level_analysis: bool | None = None
    allow_bid_recommendations: bool | None = None
    allow_negative_keyword_recommendations: bool | None = None
    allow_pause_recommendations: bool | None = None
    allow_budget_recommendations: bool | None = None
    allow_keep_running: bool | None = None
    allow_increase_bid: bool | None = None
    allow_decrease_bid: bool | None = None
    allow_pause_review: bool | None = None
    allow_negative_exact: bool | None = None
    allow_negative_phrase: bool | None = None
    allow_move_to_exact: bool | None = None
    allow_budget_review: bool | None = None
    allow_data_quality_review: bool | None = None
    allow_product_mapping_recommendations: bool | None = None
    max_bid_increase_multiplier: Decimal | None = Field(default=None, ge=Decimal("1.0000"), le=Decimal("3.0000"))
    max_bid_decrease_multiplier: Decimal | None = Field(default=None, ge=Decimal("0.1000"), le=Decimal("1.0000"))
    require_high_confidence_for_pause: bool | None = None
    require_high_confidence_for_negative_keywords: bool | None = None
    require_min_clicks_before_action: int | None = Field(default=None, ge=0)
    require_min_spend_before_action: Decimal | None = Field(default=None, ge=Decimal("0"))
    target_acos_override: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("10"))
    min_orders_for_scaling: int | None = Field(default=None, ge=0)
    min_roas_for_scaling: Decimal | None = Field(default=None, ge=Decimal("0"))
    custom_system_instruction: str | None = Field(default=None, max_length=4000)
    custom_business_goal: str | None = Field(default=None, max_length=2000)
    optimization_goal: AgentOptimizationGoal | None = None
    brand_safety_notes: str | None = Field(default=None, max_length=2000)
    competitor_notes: str | None = Field(default=None, max_length=2000)
    product_margin_notes: str | None = Field(default=None, max_length=2000)
    recommendation_language: str | None = Field(default=None, min_length=2, max_length=20)
    explanation_detail: AgentExplanationDetail | None = None
    show_raw_ai_reasoning_summary: bool | None = None
    show_metric_evidence: bool | None = None
    require_action_risk_note: bool | None = None
    chunk_strategy: AgentChunkStrategy | None = None
    reason: str = Field(default="Agent configuration updated.", min_length=1, max_length=1000)


class AgentControlRequest(BaseModel):
    reason: str = Field(default="User control action.", min_length=1, max_length=1000)


class AgentWorkflowEdge(BaseModel):
    source_agent_id: str
    target_agent_id: str
    status: str
    data_passed_summary: list[str]
    created_at: datetime | None = None
    completed_at: datetime | None = None


class AgentWorkflowNode(BaseModel):
    agent_id: str
    display_name: str
    description: str
    status: str
    mode: str
    strictness_level: str
    last_run_at: datetime | None = None
    recommendations_created: int = 0
    errors: list[str] = Field(default_factory=list)
    can_mutate_live_amazon_ads: bool = False


class AgentRunEvent(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_id: str
    agent_run_id: UUID | None = None
    monitoring_import_id: UUID | None = None
    event_type: str
    message: str
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentRunDetail(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID | None = None
    monitoring_import_id: UUID | None = None
    agent_id: str
    agent_name: str
    provider: str
    model: str
    schema_version: str
    input_hash: str
    input_json: dict = Field(default_factory=dict)
    output_json: dict = Field(default_factory=dict)
    error_json: dict = Field(default_factory=dict)
    status: str
    latency_ms: int = 0
    mode: str | None = None
    strictness_level: str | None = None
    confidence_threshold: str | None = None
    dependency_agent_run_ids: list[str] = Field(default_factory=list)
    recommendation_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stopped_at: datetime | None = None
    paused_at: datetime | None = None
    controlled_by: str | None = None
    control_reason: str | None = None
    can_mutate_live_amazon_ads: bool = False

    model_config = ConfigDict(from_attributes=True)


class AgentWorkflowResponse(BaseModel):
    monitoring_import_id: UUID
    nodes: list[AgentWorkflowNode]
    edges: list[AgentWorkflowEdge]
    events: list[AgentRunEvent]
