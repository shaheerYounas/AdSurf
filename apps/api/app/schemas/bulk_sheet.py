"""Pydantic schemas for Amazon Bulk Operations sheet imports."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BulkCampaignSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    campaign_id: str
    name: str
    status: str
    daily_budget: Decimal | None = None
    targeting_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    bidding_strategy: str | None = None


class BulkAdGroupSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ad_group_id: str
    campaign_id: str
    campaign_name: str
    name: str
    status: str
    default_bid: Decimal | None = None


class BulkKeywordSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    keyword_id: str
    campaign_id: str
    campaign_name: str
    ad_group_id: str
    ad_group_name: str
    keyword_text: str
    match_type: str
    bid: Decimal | None = None
    status: str


class BulkTargetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_id: str
    campaign_id: str
    campaign_name: str
    ad_group_id: str
    ad_group_name: str
    expression: str
    bid: Decimal | None = None
    status: str


class BulkNegativeKeywordSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    campaign_id: str
    campaign_name: str
    ad_group_id: str
    ad_group_name: str
    keyword_text: str
    match_type: str


class BulkProductAdSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ad_id: str
    campaign_id: str
    campaign_name: str
    ad_group_id: str
    ad_group_name: str
    asin: str | None = None
    sku: str | None = None
    status: str


class BulkSheetStats(BaseModel):
    total_campaigns: int
    active_campaigns: int
    total_ad_groups: int
    total_keywords: int
    total_targets: int
    total_product_ads: int
    total_negative_keywords: int


class BulkSheetSnapshotResponse(BaseModel):
    filename: str
    date_range_start: str | None = None
    date_range_end: str | None = None
    account_id: str | None = None
    stats: BulkSheetStats
    campaigns: list[BulkCampaignSchema]
    ad_groups: list[BulkAdGroupSchema]
    keywords: list[BulkKeywordSchema]
    targets: list[BulkTargetSchema]
    negative_keywords: list[BulkNegativeKeywordSchema]
    product_ads: list[BulkProductAdSchema]
    warnings: list[str] = Field(default_factory=list)
