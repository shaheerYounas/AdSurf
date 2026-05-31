"""Schemas for dual-path decision sessions — stores every AI vs deterministic comparison."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DualPathSessionStatus(str):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    FALLBACK = "fallback"  # AI failed, deterministic path used


class DualPathSession(BaseModel):
    """A single dual-path decision session — stores inputs, deterministic result, AI result, and comparison."""
    id: UUID
    workspace_id: UUID
    product_id: UUID | None = None
    agent_id: str
    mode: str  # deterministic | ai | hybrid
    provider: str | None = None
    model: str | None = None
    status: str = "pending"

    # Inputs (truncated for storage)
    input_summary_json: dict = Field(default_factory=dict)

    # Deterministic path result
    deterministic_result_json: dict | None = None
    deterministic_latency_ms: int = 0

    # AI path result
    ai_result_json: dict | None = None
    ai_latency_ms: int = 0
    ai_prompt_json: dict | None = None  # the prompt sent (truncated)
    ai_model_params_json: dict | None = None  # temperature, max_tokens, etc.

    # Comparison
    decision_source: str | None = None  # deterministic | ai | hybrid_ai | hybrid_fallback
    used_ai: bool = False
    fallback_used: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    comparison_summary_json: dict | None = None  # key differences between deterministic and AI

    # Metadata
    created_at: datetime
    completed_at: datetime | None = None
    created_by: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DualPathSessionListItem(BaseModel):
    """Lightweight session for listing."""
    id: UUID
    agent_id: str
    mode: str
    status: str
    provider: str | None = None
    model: str | None = None
    decision_source: str | None = None
    used_ai: bool = False
    fallback_used: bool = False
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DualPathSessionList(BaseModel):
    sessions: list[DualPathSessionListItem]
    total: int