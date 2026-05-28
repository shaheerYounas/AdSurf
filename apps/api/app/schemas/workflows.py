from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"
    PAUSED = "paused"


class WorkflowType(StrEnum):
    ACCOUNT_IMPORT_ANALYSIS = "account_import_analysis"
    SINGLE_PRODUCT_MONITORING = "single_product_monitoring"


class WorkflowEventType(StrEnum):
    WORKFLOW_STARTED = "workflow_started"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    LLM_CALL_STARTED = "llm_call_started"
    LLM_CALL_COMPLETED = "llm_call_completed"
    LLM_CALL_FAILED = "llm_call_failed"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"
    FALLBACK_USED = "fallback_used"
    RECOMMENDATION_VALIDATED = "recommendation_validated"
    RECOMMENDATION_REJECTED = "recommendation_rejected"
    HUMAN_APPROVAL_WAITING = "human_approval_waiting"
    USER_APPROVED = "user_approved"
    USER_REJECTED = "user_rejected"
    WORKFLOW_COMPLETED = "workflow_completed"


class AgentWorkflow(BaseModel):
    id: UUID
    workspace_id: UUID
    account_import_id: UUID | None = None
    upload_id: UUID | None = None
    product_id: UUID | None = None
    monitoring_import_id: UUID | None = None
    workflow_type: WorkflowType = WorkflowType.ACCOUNT_IMPORT_ANALYSIS
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_node: str | None = None
    state_json: dict = Field(default_factory=dict)
    error_json: dict = Field(default_factory=dict)
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentWorkflowCheckpoint(BaseModel):
    id: UUID
    workflow_id: UUID
    node_name: str
    state_json: dict = Field(default_factory=dict)
    status: WorkflowStatus | str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentWorkflowEvent(BaseModel):
    id: UUID
    workflow_id: UUID
    workspace_id: UUID
    agent_id: str | None = None
    node_name: str
    event_type: WorkflowEventType | str
    message: str
    metadata_json: dict = Field(default_factory=dict)
    latency_ms: int | None = None
    provider: str | None = None
    model: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowSummaryResponse(BaseModel):
    workflow: AgentWorkflow
    progress: dict = Field(default_factory=dict)
    latest_events: list[AgentWorkflowEvent] = Field(default_factory=list)


class WorkflowControlRequest(BaseModel):
    reason: str = Field(default="User requested workflow control.", min_length=1, max_length=1000)
