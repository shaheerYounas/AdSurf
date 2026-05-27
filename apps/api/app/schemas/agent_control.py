from datetime import datetime
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
    strictness_level: AgentStrictnessLevel = AgentStrictnessLevel.BALANCED
    confidence_threshold: AgentConfidenceThreshold = AgentConfidenceThreshold.MEDIUM
    max_recommendations: int = Field(default=100, ge=1, le=1000)
    allow_bid_recommendations: bool = True
    allow_negative_keyword_recommendations: bool = True
    allow_pause_recommendations: bool = True
    allow_budget_recommendations: bool = True
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentConfigPatch(BaseModel):
    product_id: UUID | None = None
    enabled: bool | None = None
    mode: AgentMode | None = None
    strictness_level: AgentStrictnessLevel | None = None
    confidence_threshold: AgentConfidenceThreshold | None = None
    max_recommendations: int | None = Field(default=None, ge=1, le=1000)
    allow_bid_recommendations: bool | None = None
    allow_negative_keyword_recommendations: bool | None = None
    allow_pause_recommendations: bool | None = None
    allow_budget_recommendations: bool | None = None
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
