from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrategyMode(StrEnum):
    PROFIT = "profit"
    GROWTH = "growth"
    LAUNCH = "launch"
    RANK_DEFENSE = "rank_defense"
    INVENTORY_CLEARANCE = "inventory_clearance"
    BRAND_DEFENSE = "brand_defense"
    COMPETITOR_CONQUESTING = "competitor_conquesting"
    WASTED_SPEND_CLEANUP = "wasted_spend_cleanup"


class StrategyRiskTolerance(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class AccountStrategy(BaseModel):
    id: UUID
    workspace_id: UUID
    mode: StrategyMode = StrategyMode.PROFIT
    risk_tolerance: StrategyRiskTolerance = StrategyRiskTolerance.MODERATE
    max_bid_increase_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    max_bid_decrease_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    max_budget_increase_pct: float = Field(default=30.0, ge=0.0, le=200.0)
    max_daily_budget_per_campaign: float | None = Field(default=None, ge=0.0)
    allow_auto_pause: bool = False
    allow_negative_keywords: bool = True
    allow_new_campaign_creation: bool = False
    min_confidence_for_auto_approve: str = Field(default="high")
    require_approval_for_bid_increase: bool = True
    require_approval_for_bid_decrease: bool = False
    require_approval_for_negative_keywords: bool = True
    require_approval_for_budget_changes: bool = True
    require_approval_for_pause: bool = True
    require_approval_for_new_campaigns: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountStrategyUpdate(BaseModel):
    mode: StrategyMode | None = None
    risk_tolerance: StrategyRiskTolerance | None = None
    max_bid_increase_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    max_bid_decrease_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    max_budget_increase_pct: float | None = Field(default=None, ge=0.0, le=200.0)
    max_daily_budget_per_campaign: float | None = Field(default=None, ge=0.0)
    allow_auto_pause: bool | None = None
    allow_negative_keywords: bool | None = None
    allow_new_campaign_creation: bool | None = None
    min_confidence_for_auto_approve: str | None = None
    require_approval_for_bid_increase: bool | None = None
    require_approval_for_bid_decrease: bool | None = None
    require_approval_for_negative_keywords: bool | None = None
    require_approval_for_budget_changes: bool | None = None
    require_approval_for_pause: bool | None = None
    require_approval_for_new_campaigns: bool | None = None


DEFAULT_STRATEGY_CONFIG = {
    StrategyMode.PROFIT: {
        "risk_tolerance": StrategyRiskTolerance.CONSERVATIVE,
        "max_bid_increase_pct": 10.0,
        "max_bid_decrease_pct": 60.0,
        "max_budget_increase_pct": 20.0,
        "acos_multiplier_threshold": 1.10,
        "roas_minimum": 2.0,
        "allow_negative_keywords": True,
        "allow_new_campaign_creation": False,
        "description": "Prioritize profitable ACOS. Decrease wasteful bids aggressively. Conservative increases only for proven winners.",
    },
    StrategyMode.GROWTH: {
        "risk_tolerance": StrategyRiskTolerance.AGGRESSIVE,
        "max_bid_increase_pct": 30.0,
        "max_bid_decrease_pct": 30.0,
        "max_budget_increase_pct": 50.0,
        "acos_multiplier_threshold": 1.50,
        "roas_minimum": 1.0,
        "allow_negative_keywords": True,
        "allow_new_campaign_creation": True,
        "description": "Maximize visibility and sales volume. Accept higher ACOS for growth. Aggressive bid increases on converting terms.",
    },
    StrategyMode.LAUNCH: {
        "risk_tolerance": StrategyRiskTolerance.AGGRESSIVE,
        "max_bid_increase_pct": 50.0,
        "max_bid_decrease_pct": 20.0,
        "max_budget_increase_pct": 100.0,
        "acos_multiplier_threshold": 3.0,
        "roas_minimum": 0.5,
        "allow_negative_keywords": False,
        "allow_new_campaign_creation": True,
        "description": "Product launch mode. Maximize data collection. Tolerate high ACOS. Do not add negatives during data gathering.",
    },
    StrategyMode.RANK_DEFENSE: {
        "risk_tolerance": StrategyRiskTolerance.MODERATE,
        "max_bid_increase_pct": 25.0,
        "max_bid_decrease_pct": 40.0,
        "max_budget_increase_pct": 30.0,
        "acos_multiplier_threshold": 1.25,
        "roas_minimum": 1.5,
        "allow_negative_keywords": True,
        "allow_new_campaign_creation": False,
        "description": "Defend organic rank with PPC. Maintain visibility on key terms. Accept moderate ACOS for rank protection.",
    },
    StrategyMode.INVENTORY_CLEARANCE: {
        "risk_tolerance": StrategyRiskTolerance.AGGRESSIVE,
        "max_bid_increase_pct": 40.0,
        "max_bid_decrease_pct": 50.0,
        "max_budget_increase_pct": 80.0,
        "acos_multiplier_threshold": 2.0,
        "roas_minimum": 0.5,
        "allow_negative_keywords": True,
        "allow_new_campaign_creation": True,
        "description": "Clear excess inventory. Maximize sales velocity. Accept lower ROAS. Aggressive on converting terms.",
    },
    StrategyMode.BRAND_DEFENSE: {
        "risk_tolerance": StrategyRiskTolerance.MODERATE,
        "max_bid_increase_pct": 20.0,
        "max_bid_decrease_pct": 40.0,
        "max_budget_increase_pct": 25.0,
        "acos_multiplier_threshold": 1.20,
        "roas_minimum": 2.0,
        "allow_negative_keywords": True,
        "allow_new_campaign_creation": False,
        "description": "Protect branded search terms from competitors. Maintain top-of-search placement. Moderate spend.",
    },
    StrategyMode.COMPETITOR_CONQUESTING: {
        "risk_tolerance": StrategyRiskTolerance.AGGRESSIVE,
        "max_bid_increase_pct": 35.0,
        "max_bid_decrease_pct": 30.0,
        "max_budget_increase_pct": 40.0,
        "acos_multiplier_threshold": 2.0,
        "roas_minimum": 1.0,
        "allow_negative_keywords": True,
        "allow_new_campaign_creation": True,
        "description": "Target competitor keywords and ASINs. Accept higher ACOS for conquest. Aggressive on competitor terms.",
    },
    StrategyMode.WASTED_SPEND_CLEANUP: {
        "risk_tolerance": StrategyRiskTolerance.CONSERVATIVE,
        "max_bid_increase_pct": 5.0,
        "max_bid_decrease_pct": 70.0,
        "max_budget_increase_pct": 10.0,
        "acos_multiplier_threshold": 1.05,
        "roas_minimum": 3.0,
        "allow_negative_keywords": True,
        "allow_new_campaign_creation": False,
        "description": "Aggressively cut wasted spend. Add negatives. Decrease bids on underperformers. No increases unless very strong.",
    },
}