from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from apps.api.app.core.auth import (
    PRODUCT_PROFILE_READ_ROLES,
    PRODUCT_PROFILE_WRITE_ROLES,
    WorkspacePrincipal,
    require_workspace_member,
)
from apps.api.app.core.database import get_database_engine
from apps.api.app.schemas.envelope import success_response
from apps.api.app.schemas.marketing_pipeline import (
    CampaignPlanRequest,
    CompetitorResearchRequest,
    MonitoringRequest,
)
from apps.api.app.services.competitor_research_pipeline import (
    ApprovedKeyword,
    CompetitorResearchPipeline,
    parse_csv_rows,
)
from apps.api.app.services.marketing_campaign_builder import MarketingCampaignBuilder
from apps.api.app.services.marketing_monitoring_service import (
    CampaignDayRecord,
    MarketingMonitoringService,
    MonitoringReport,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_campaign_spec(spec) -> dict:
    return {
        "name": spec.name,
        "match_type": str(spec.match_type),
        "daily_budget": str(spec.daily_budget),
        "is_hero": spec.is_hero,
        "ad_groups": [
            {
                "name": ag.name,
                "keyword": ag.keyword,
                "bid": str(ag.bid),
                "match_type": str(ag.match_type),
            }
            for ag in spec.ad_groups
        ],
        "negative_keywords": [
            {"keyword": nk.keyword, "match_type": str(nk.match_type)}
            for nk in spec.negative_keywords
        ],
    }


def _serialize_report(report: MonitoringReport) -> dict:
    return {
        "campaign_id": report.campaign_id,
        "final_bid": str(report.final_bid),
        "is_locked": report.is_locked,
        "day7_acos": str(report.day7_acos) if report.day7_acos is not None else None,
        "actions": [
            {
                "campaign_id": a.campaign_id,
                "day_number": a.day_number,
                "action_type": str(a.action_type),
                "new_bid": str(a.new_bid) if a.new_bid is not None else None,
                "reason": a.reason,
                "acos": str(a.acos) if a.acos is not None else None,
            }
            for a in report.actions
        ],
    }


# ---------------------------------------------------------------------------
# 1. POST competitor-research
# ---------------------------------------------------------------------------

@router.post(
    "/workspaces/{workspace_id}/marketing/competitor-research",
    status_code=status.HTTP_201_CREATED,
)
def create_competitor_research(
    workspace_id: UUID,
    payload: CompetitorResearchRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    engine=Depends(get_database_engine),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    rows = parse_csv_rows(payload.csv_text)
    result = CompetitorResearchPipeline().run(rows=rows, product_name=payload.product_name)

    run_id = str(uuid4())
    approved_keywords_json = json.dumps(
        [
            {
                "keyword": kw.keyword,
                "search_volume": kw.search_volume,
                "relevance_score": kw.relevance_score,
                "amazon_verified": kw.amazon_verified,
            }
            for kw in result.approved_keywords
        ]
    )

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO marketing_research_runs
                    (id, workspace_id, product_name, status,
                     total_input_keywords, filtered_by_score, filtered_by_amazon,
                     approved_keywords_json, created_at)
                VALUES
                    (:id, :workspace_id, :product_name, 'completed',
                     :total_input_keywords, :filtered_by_score, :filtered_by_amazon,
                     :approved_keywords_json, :created_at)
                """
            ),
            {
                "id": run_id,
                "workspace_id": str(workspace_id),
                "product_name": payload.product_name,
                "total_input_keywords": result.total_input_keywords,
                "filtered_by_score": result.filtered_by_score,
                "filtered_by_amazon": result.filtered_by_amazon,
                "approved_keywords_json": approved_keywords_json,
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        conn.commit()

    return success_response(
        data={
            "run_id": run_id,
            "total_input_keywords": result.total_input_keywords,
            "filtered_by_score": result.filtered_by_score,
            "filtered_by_amazon": result.filtered_by_amazon,
            "approved_keywords": len(result.approved_keywords),
        }
    )


# ---------------------------------------------------------------------------
# 2. GET competitor-research/{run_id}
# ---------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/marketing/competitor-research/{run_id}")
def get_competitor_research(
    workspace_id: UUID,
    run_id: str,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    engine=Depends(get_database_engine),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, workspace_id, product_name, status,
                       total_input_keywords, filtered_by_score, filtered_by_amazon,
                       approved_keywords_json, created_at
                FROM marketing_research_runs
                WHERE id = :run_id AND workspace_id = :workspace_id
                """
            ),
            {"run_id": run_id, "workspace_id": str(workspace_id)},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Competitor research run not found.")

    record = dict(row._mapping)
    if isinstance(record.get("approved_keywords_json"), str):
        record["approved_keywords_json"] = json.loads(record["approved_keywords_json"])

    return success_response(data=record)


# ---------------------------------------------------------------------------
# 3. POST campaign-plans
# ---------------------------------------------------------------------------

@router.post(
    "/workspaces/{workspace_id}/marketing/campaign-plans",
    status_code=status.HTTP_201_CREATED,
)
def create_campaign_plan(
    workspace_id: UUID,
    payload: CampaignPlanRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    engine=Depends(get_database_engine),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT approved_keywords_json
                FROM marketing_research_runs
                WHERE id = :run_id AND workspace_id = :workspace_id
                """
            ),
            {"run_id": payload.research_run_id, "workspace_id": str(workspace_id)},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Research run not found.")

    raw_keywords = row._mapping["approved_keywords_json"]
    if isinstance(raw_keywords, str):
        raw_keywords = json.loads(raw_keywords)

    approved_keywords = [
        ApprovedKeyword(
            keyword=kw["keyword"],
            search_volume=int(kw["search_volume"]),
            relevance_score=int(kw["relevance_score"]),
            amazon_verified=bool(kw["amazon_verified"]),
        )
        for kw in raw_keywords
    ]

    plan = MarketingCampaignBuilder().build(
        approved_keywords=approved_keywords,
        product_name=payload.product_name,
        created_date=payload.created_date,
    )

    plan_id = str(uuid4())
    hero_json = json.dumps(_serialize_campaign_spec(plan.hero_campaign))
    grouped_json = json.dumps([_serialize_campaign_spec(c) for c in plan.grouped_campaigns])

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO marketing_campaign_plans
                    (id, workspace_id, research_run_id, product_name, status,
                     hero_campaign_json, grouped_campaigns_json,
                     total_keywords, batch_count, created_at)
                VALUES
                    (:id, :workspace_id, :research_run_id, :product_name, 'draft',
                     :hero_campaign_json, :grouped_campaigns_json,
                     :total_keywords, :batch_count, :created_at)
                """
            ),
            {
                "id": plan_id,
                "workspace_id": str(workspace_id),
                "research_run_id": payload.research_run_id,
                "product_name": payload.product_name,
                "hero_campaign_json": hero_json,
                "grouped_campaigns_json": grouped_json,
                "total_keywords": plan.total_keywords,
                "batch_count": plan.batch_count,
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        conn.commit()

    return success_response(
        data={
            "plan_id": plan_id,
            "product_name": payload.product_name,
            "total_keywords": plan.total_keywords,
            "batch_count": plan.batch_count,
            "hero_campaign_name": plan.hero_campaign.name,
            "grouped_campaign_count": len(plan.grouped_campaigns),
        }
    )


# ---------------------------------------------------------------------------
# 4. GET campaign-plans/{plan_id}
# ---------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/marketing/campaign-plans/{plan_id}")
def get_campaign_plan(
    workspace_id: UUID,
    plan_id: str,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    engine=Depends(get_database_engine),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, workspace_id, research_run_id, product_name, status,
                       hero_campaign_json, grouped_campaigns_json,
                       total_keywords, batch_count, created_at
                FROM marketing_campaign_plans
                WHERE id = :plan_id AND workspace_id = :workspace_id
                """
            ),
            {"plan_id": plan_id, "workspace_id": str(workspace_id)},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Campaign plan not found.")

    record = dict(row._mapping)
    for key in ("hero_campaign_json", "grouped_campaigns_json"):
        if isinstance(record.get(key), str):
            record[key] = json.loads(record[key])

    return success_response(data=record)


# ---------------------------------------------------------------------------
# 5. POST monitoring
# ---------------------------------------------------------------------------

@router.post(
    "/workspaces/{workspace_id}/marketing/monitoring",
    status_code=status.HTTP_201_CREATED,
)
def run_marketing_monitoring(
    workspace_id: UUID,
    payload: MonitoringRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    engine=Depends(get_database_engine),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    day_records: list[CampaignDayRecord] = [
        CampaignDayRecord(
            campaign_id=item.campaign_id,
            day_number=item.day_number,
            daily_spend=Decimal(str(item.daily_spend)),
            daily_budget=Decimal(str(item.daily_budget)),
            current_bid=Decimal(str(item.current_bid)),
            total_spend_to_date=Decimal(str(item.total_spend_to_date)),
            total_sales_to_date=Decimal(str(item.total_sales_to_date)),
            is_locked=item.is_locked,
        )
        for item in payload.day_records
    ]

    reports = MarketingMonitoringService().run_14_day_simulation(day_records)

    # Persist one row per action (each action has a valid day_number 1-14)
    inserted = 0
    with engine.connect() as conn:
        for report in reports:
            for action in report.actions:
                conn.execute(
                    text(
                        """
                        INSERT INTO marketing_monitoring_records
                            (id, workspace_id, campaign_plan_id, campaign_id,
                             day_number, current_bid, is_locked,
                             action_taken, new_bid, acos, action_reason, created_at)
                        VALUES
                            (:id, :workspace_id, :campaign_plan_id, :campaign_id,
                             :day_number, :current_bid, :is_locked,
                             :action_taken, :new_bid, :acos, :action_reason, :created_at)
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "workspace_id": str(workspace_id),
                        "campaign_plan_id": payload.campaign_plan_id,
                        "campaign_id": action.campaign_id,
                        "day_number": action.day_number,
                        "current_bid": str(report.final_bid),
                        "is_locked": report.is_locked,
                        "action_taken": str(action.action_type),
                        "new_bid": str(action.new_bid) if action.new_bid is not None else None,
                        "acos": str(action.acos) if action.acos is not None else None,
                        "action_reason": action.reason,
                        "created_at": datetime.utcnow().isoformat(),
                    },
                )
                inserted += 1
        conn.commit()

    return success_response(
        data={
            "campaign_plan_id": payload.campaign_plan_id,
            "records_created": inserted,
            "monitoring_reports": [_serialize_report(r) for r in reports],
        }
    )
