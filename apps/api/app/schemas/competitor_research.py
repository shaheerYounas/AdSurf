"""Pydantic schemas for live Amazon competitor research."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompetitorResearchStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED_MANUAL_VERIFICATION = "paused_manual_verification"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CompetitorKeywordStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class CompetitorKeywordSource(StrEnum):
    USER_SEED = "user_seed"
    SEARCH_TERM_REPORT = "search_term_report"
    HIGH_SPEND = "high_spend"
    MOVE_TO_EXACT = "move_to_exact"
    MANUAL = "manual"


# ─── Run settings ─────────────────────────────────────────────────────────────


class CompetitorResearchRunSettings(BaseModel):
    marketplace: str = Field(default="US", description="Amazon marketplace code (US, CA, UK, DE, ...)")
    max_keywords_per_run: int = Field(default=20, ge=1, le=100)
    max_competitors_per_keyword: int = Field(default=10, ge=1, le=25)
    delay_min_seconds: float = Field(default=2.0, ge=0.5, le=30.0)
    delay_max_seconds: float = Field(default=5.0, ge=1.0, le=60.0)
    open_product_detail_pages: bool = False
    headless: bool = False  # visible browser by default


class CompetitorResearchCreateRequest(BaseModel):
    product_id: UUID | None = None
    settings: CompetitorResearchRunSettings = Field(default_factory=CompetitorResearchRunSettings)

    # Keyword sources (at least one required)
    seed_keywords: list[str] = Field(default_factory=list, description="User-typed seed keywords")
    include_high_spend_terms: bool = True
    include_move_to_exact_terms: bool = True
    manual_keywords: list[str] = Field(default_factory=list)


# ─── Keyword queue entry ───────────────────────────────────────────────────────


class CompetitorResearchKeyword(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    keyword: str
    keyword_source: CompetitorKeywordSource | None = None
    priority_rank: int
    status: CompetitorKeywordStatus
    search_url: str | None = None
    searched_at: datetime | None = None
    screenshot_path: str | None = None
    organic_count: int | None = None
    sponsored_count: int | None = None
    error_message: str | None = None


# ─── Captured competitor product ──────────────────────────────────────────────


class CompetitorResearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    keyword_id: UUID
    position: int
    result_type: str  # 'organic' | 'sponsored'

    asin: str | None = None
    title: str | None = None
    brand: str | None = None
    price_text: str | None = None
    price_usd: Decimal | None = None
    rating: Decimal | None = None
    review_count: int | None = None
    has_coupon: bool | None = None
    is_prime: bool | None = None
    is_amazon_choice: bool | None = None
    is_best_seller: bool | None = None
    image_url: str | None = None
    product_url: str | None = None

    # Product detail page enrichment
    detail_bullets_json: list[str] | None = None
    detail_variations: int | None = None
    detail_aplus_present: bool | None = None
    detail_image_count: int | None = None


# ─── AI insight per keyword ────────────────────────────────────────────────────


class CompetitorAiInsight(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    keyword_id: UUID
    keyword: str

    opportunity_score: int | None = Field(default=None, ge=0, le=100)
    competitor_strength_score: int | None = Field(default=None, ge=0, le=100)
    relevance_score: int | None = Field(default=None, ge=0, le=100)
    risk_score: int | None = Field(default=None, ge=0, le=100)

    competitor_strength: str | None = None
    sponsored_intensity: str | None = None
    organic_difficulty: str | None = None
    product_market_fit: str | None = None

    avg_price_range: str | None = None
    avg_review_count: str | None = None
    avg_price_min_usd: Decimal | None = None
    avg_price_max_usd: Decimal | None = None
    avg_review_count_number: int | None = None

    recommended_ad_strategy: str | None = None
    listing_improvement: str | None = None
    action_recommendation: str | None = None

    full_summary: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    generated_at: datetime


# ─── Run summary ──────────────────────────────────────────────────────────────


class CompetitorResearchRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None = None

    marketplace: str
    max_keywords_per_run: int
    max_competitors_per_keyword: int
    delay_min_seconds: float
    delay_max_seconds: float
    open_product_detail_pages: bool
    headless: bool

    status: CompetitorResearchStatus
    keywords_total: int
    keywords_completed: int
    keywords_failed: int
    products_captured: int
    current_keyword_index: int
    paused_reason: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class CompetitorResearchRunDetail(CompetitorResearchRun):
    """Run with its keyword queue and AI insights."""

    keywords: list[CompetitorResearchKeyword] = Field(default_factory=list)
    insights: list[CompetitorAiInsight] = Field(default_factory=list)


# ─── Control actions ──────────────────────────────────────────────────────────


class CompetitorResearchControlRequest(BaseModel):
    action: str  # 'pause' | 'resume' | 'cancel'
    reason: str | None = None
