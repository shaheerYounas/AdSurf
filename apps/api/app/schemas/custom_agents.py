"""Schemas for the custom agent builder system."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class AgentStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ToolPermissionLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class AgentModelProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    LOCAL = "local"


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"
    TABLE = "table"
    CODE = "code"
    EMAIL = "email"


class WorkflowType(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    SUPERVISOR = "supervisor"
    CUSTOM = "custom"


class MemoryType(StrEnum):
    PREFERENCE = "preference"
    FACT = "fact"
    DECISION = "decision"
    CONTEXT = "context"
    USER_INFO = "user_info"
    PROJECT = "project"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"


class StepType(StrEnum):
    PLANNER = "planner"
    RESEARCH = "research"
    TOOL_CALL = "tool_call"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    LLM_CALL = "llm_call"
    SUB_AGENT = "sub_agent"
    REVIEWER = "reviewer"
    OUTPUT_FORMAT = "output_format"
    APPROVAL_CHECK = "approval_check"


class KnowledgeBaseStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


# ── Custom Agent ─────────────────────────────────────────────────────────────

class CustomAgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    role_instructions: str | None = Field(default=None, max_length=8000)
    model_provider: AgentModelProvider = AgentModelProvider.DEEPSEEK
    model_name: str = "deepseek-chat"
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    memory_enabled: bool = False
    memory_ttl_days: int = Field(default=30, ge=1, le=365)
    output_format: OutputFormat = OutputFormat.TEXT
    output_schema: dict | None = None
    workflow_type: WorkflowType = WorkflowType.SEQUENTIAL
    workflow_graph: dict | None = None
    status: AgentStatus = AgentStatus.DRAFT
    metadata_json: dict = Field(default_factory=dict)


class CustomAgentCreate(CustomAgentBase):
    workspace_id: UUID
    created_by: UUID | None = None


class CustomAgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    role_instructions: str | None = Field(default=None, max_length=8000)
    model_provider: AgentModelProvider | None = None
    model_name: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    memory_enabled: bool | None = None
    memory_ttl_days: int | None = Field(default=None, ge=1, le=365)
    output_format: OutputFormat | None = None
    output_schema: dict | None = None
    workflow_type: WorkflowType | None = None
    workflow_graph: dict | None = None
    status: AgentStatus | None = None
    metadata_json: dict | None = None
    updated_by: UUID | None = None


class CustomAgentResponse(CustomAgentBase):
    id: UUID
    workspace_id: UUID
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    tools: list["AgentToolResponse"] = Field(default_factory=list)
    sub_agents: list["SubAgentResponse"] = Field(default_factory=list)
    knowledge_base_ids: list[UUID] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CustomAgentSummary(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    model_provider: AgentModelProvider
    model_name: str
    memory_enabled: bool
    status: AgentStatus
    created_at: datetime
    updated_at: datetime
    tool_count: int = 0
    sub_agent_count: int = 0
    thread_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# ── Agent Tools ──────────────────────────────────────────────────────────────

class AgentToolBase(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=100)
    tool_config: dict = Field(default_factory=dict)
    enabled: bool = True
    permission_level: ToolPermissionLevel = ToolPermissionLevel.READ
    requires_approval: bool = False
    rate_limit_per_day: int | None = None
    allowed_domains: list[str] | None = None
    allowed_actions: list[str] | None = None


class AgentToolCreate(AgentToolBase):
    agent_id: UUID


class AgentToolUpdate(BaseModel):
    tool_config: dict | None = None
    enabled: bool | None = None
    permission_level: ToolPermissionLevel | None = None
    requires_approval: bool | None = None
    rate_limit_per_day: int | None = None
    allowed_domains: list[str] | None = None
    allowed_actions: list[str] | None = None


class AgentToolResponse(AgentToolBase):
    id: UUID
    workspace_id: UUID
    agent_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Knowledge Bases ──────────────────────────────────────────────────────────

class KnowledgeBaseBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    source_type: str = "upload"
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"


class KnowledgeBaseCreate(KnowledgeBaseBase):
    workspace_id: UUID
    created_by: UUID | None = None


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class KnowledgeBaseResponse(KnowledgeBaseBase):
    id: UUID
    workspace_id: UUID
    file_count: int = 0
    chunk_count: int = 0
    status: KnowledgeBaseStatus
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    files: list["KnowledgeBaseFileResponse"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class KnowledgeBaseFileResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    file_name: str
    file_path: str
    file_type: str
    file_size_bytes: int | None = None
    chunk_count: int = 0
    status: KnowledgeBaseStatus
    error_message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentKnowledgeBaseLink(BaseModel):
    agent_id: UUID
    knowledge_base_id: UUID
    retrieval_priority: int = Field(default=1, ge=1, le=10)
    max_chunks_per_query: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.75, ge=0, le=1)


# ── Sub-Agents ───────────────────────────────────────────────────────────────

class SubAgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=100)
    instructions: str = Field(..., min_length=1, max_length=8000)
    model_provider: AgentModelProvider | None = None
    model_name: str | None = None
    tools_json: list[str] = Field(default_factory=list)
    execution_order: int = Field(default=1, ge=1)
    enabled: bool = True
    requires_approval: bool = False


class SubAgentCreate(SubAgentBase):
    parent_agent_id: UUID


class SubAgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=100)
    instructions: str | None = Field(default=None, max_length=8000)
    model_provider: AgentModelProvider | None = None
    model_name: str | None = None
    tools_json: list[str] | None = None
    execution_order: int | None = Field(default=None, ge=1)
    enabled: bool | None = None
    requires_approval: bool | None = None


class SubAgentResponse(SubAgentBase):
    id: UUID
    workspace_id: UUID
    parent_agent_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Agent Threads ────────────────────────────────────────────────────────────

class AgentThreadCreate(BaseModel):
    agent_id: UUID
    title: str | None = Field(default=None, max_length=500)
    created_by: UUID | None = None
    metadata_json: dict = Field(default_factory=dict)


class AgentThreadUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    status: str | None = None


class AgentThreadResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_id: UUID
    title: str | None
    status: str
    metadata_json: dict
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Messages ─────────────────────────────────────────────────────────────────

class AgentMessageCreate(BaseModel):
    thread_id: UUID
    agent_id: UUID | None = None
    role: str = Field(..., pattern=r"^(user|assistant|system|tool|sub_agent)$")
    content: str | None = None
    tool_calls_json: list[dict] | None = None
    tool_call_id: str | None = None
    sub_agent_name: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class AgentMessageResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    thread_id: UUID
    agent_id: UUID | None
    role: str
    content: str | None
    tool_calls_json: list[dict] | None = None
    tool_call_id: str | None = None
    sub_agent_name: str | None = None
    token_count: int | None = None
    metadata_json: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Agent Memories ───────────────────────────────────────────────────────────

class AgentMemoryCreate(BaseModel):
    agent_id: UUID
    thread_id: UUID | None = None
    memory_type: MemoryType = MemoryType.PREFERENCE
    content: str = Field(..., min_length=1, max_length=5000)
    importance: float = Field(default=0.5, ge=0, le=1)
    expires_at: datetime | None = None
    metadata_json: dict = Field(default_factory=dict)


class AgentMemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    importance: float | None = Field(default=None, ge=0, le=1)
    metadata_json: dict | None = None


class AgentMemoryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_id: UUID
    thread_id: UUID | None
    memory_type: MemoryType
    content: str
    importance: float
    access_count: int
    last_accessed_at: datetime | None
    expires_at: datetime | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Custom Agent Runs ────────────────────────────────────────────────────────

class CustomAgentRunResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_id: UUID
    thread_id: UUID | None
    status: str
    model_provider: str | None
    model_name: str | None
    input_json: dict
    output_json: dict
    error_json: dict
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0
    latency_ms: int | None
    sub_agent_runs_json: list[dict]
    tool_call_count: int = 0
    knowledge_chunks_retrieved: int = 0
    metadata_json: dict
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    steps: list["CustomAgentRunStepResponse"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CustomAgentRunStepResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    run_id: UUID
    agent_name: str | None
    step_type: str
    step_order: int
    input_json: dict
    output_json: dict
    status: str
    error_message: str | None
    latency_ms: int | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


# ── Agent Templates ──────────────────────────────────────────────────────────

class AgentTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: str
    category: str
    config_json: dict
    is_public: bool
    usage_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Agent Run Request ────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    thread_id: UUID | None = None
    message: str = Field(..., min_length=1, max_length=10000)
    metadata_json: dict = Field(default_factory=dict)


# ── Agent Chat Response (for streaming) ──────────────────────────────────────

class AgentChatResponse(BaseModel):
    run_id: UUID
    thread_id: UUID
    message: AgentMessageResponse | None = None
    status: str
    error: str | None = None


# ── Available Tools Catalog ──────────────────────────────────────────────────

class AvailableTool(BaseModel):
    tool_name: str
    display_name: str
    description: str
    category: str  # 'communication', 'development', 'data', 'web', 'business'
    default_permission_level: ToolPermissionLevel = ToolPermissionLevel.READ
    requires_approval_by_default: bool = False
    is_dangerous: bool = False


# ── Resolve forward references ───────────────────────────────────────────────

CustomAgentResponse.model_rebuild()
KnowledgeBaseResponse.model_rebuild()
CustomAgentRunResponse.model_rebuild()