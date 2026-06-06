from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CompetitorResearchRequest(BaseModel):
    csv_text: str
    product_name: str


class CompetitorResearchRunResponse(BaseModel):
    run_id: str
    product_name: str
    status: str
    total_input_keywords: int
    filtered_by_score: int
    filtered_by_amazon: int
    approved_keywords_count: int
    approved_keywords: list[dict] = []

    model_config = ConfigDict(from_attributes=True)


class CampaignPlanRequest(BaseModel):
    research_run_id: str
    product_name: str
    created_date: str = ""


class CampaignPlanResponse(BaseModel):
    plan_id: str
    product_name: str
    status: str
    total_keywords: int
    batch_count: int
    hero_campaign: dict
    grouped_campaigns: list[dict] = []

    model_config = ConfigDict(from_attributes=True)


class DayRecordInput(BaseModel):
    campaign_id: str
    day_number: int
    daily_spend: float
    daily_budget: float = 10.0
    current_bid: float = 1.0
    total_spend_to_date: float
    total_sales_to_date: float
    is_locked: bool = False


class MonitoringRequest(BaseModel):
    campaign_plan_id: str
    day_records: list[DayRecordInput]


class MonitoringActionResponse(BaseModel):
    campaign_id: str
    day_number: int
    action_type: str
    new_bid: float | None
    reason: str
    acos: float | None = None


class MonitoringReportResponse(BaseModel):
    campaign_id: str
    final_bid: float
    is_locked: bool
    day7_acos: float | None
    actions: list[MonitoringActionResponse]

    model_config = ConfigDict(from_attributes=True)
