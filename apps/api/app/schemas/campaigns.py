from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CampaignPlanStatus(StrEnum):
    GENERATED = "generated"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class BulkExportStatus(StrEnum):
    APPROVED = "approved"
    FAILED = "failed"


class CampaignPlanCreateRequest(BaseModel):
    approved_keyword_set_id: UUID


class CampaignPlanApproveRequest(BaseModel):
    approval_note: str = Field(min_length=1, max_length=1000)


class BulkExportCreateRequest(BaseModel):
    approval_note: str = Field(min_length=1, max_length=1000)
    format: str = Field(default="csv", pattern="^csv$")


class CampaignKeyword(BaseModel):
    keyword_candidate_id: UUID
    search_term: str
    search_volume: Decimal | None = None
    relevance_score: int
    bid: Decimal


class CampaignGroup(BaseModel):
    group_type: str
    group_index: int
    keywords: list[CampaignKeyword]


class GeneratedCampaign(BaseModel):
    campaign_name: str
    ad_group_name: str
    match_type: str
    daily_budget: Decimal
    keywords: list[CampaignKeyword]
    negative_keywords: list[dict]


class CampaignPlan(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    approved_keyword_set_id: UUID
    version: int
    status: CampaignPlanStatus
    rule_version_id: str
    plan_json: dict
    created_by: str
    approved_by: str | None = None
    approval_note: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BulkExport(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    campaign_plan_id: UUID
    status: BulkExportStatus
    storage_path: str
    original_filename: str
    rows_json: list[dict]
    approved_by: str
    approval_note: str
    approved_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BulkExportResponse(BaseModel):
    export: BulkExport
    download_url: str
