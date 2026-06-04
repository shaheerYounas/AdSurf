"""Schemas for AI-recommended column mapping."""

from pydantic import BaseModel, ConfigDict, Field


class AiColumnMappingRecommendRequest(BaseModel):
    column_profile_id: str


class AiSuggestedMapping(BaseModel):
    search_term: str | None = None
    search_volume: str | None = None
    competitor_rank_columns: list[str] = Field(default_factory=list)
    confidence: str = "medium"  # high | medium | low
    reasoning: str = ""

    model_config = ConfigDict(extra="allow")


class AiColumnMappingRecommendResponse(BaseModel):
    suggested_mapping: AiSuggestedMapping
    decision_source: str  # ai | hybrid_ai | deterministic
    requires_human_approval: bool = True
    executes_live_amazon_change: bool = False
    validation_messages: list[dict] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")