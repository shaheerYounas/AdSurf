"""Insights API — Backtest, Planner, Calibration, Significance endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from apps.api.app.core.auth import (
    PRODUCT_PROFILE_READ_ROLES,
    WorkspacePrincipal,
    require_workspace_member,
)
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.monitoring import MonitoringRepository, get_monitoring_repository
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.schemas.envelope import success_response
from apps.api.app.services.backtest_service import project_recommendation_impact
from apps.api.app.services.planner_agent import plan_agent_execution
from apps.api.app.services.rule_calibration import calibrate_rules_from_feedback, get_calibrated_value
from apps.api.app.services.statistical_significance import evaluate_recommendation_significance

router = APIRouter()


# ── Backtest / Counterfactual Simulation ────────────────────────────────

@router.post("/workspaces/{workspace_id}/recommendations/{recommendation_id}/backtest")
def backtest_recommendation(
    workspace_id: UUID,
    recommendation_id: UUID,
    window_days: int = Query(default=14, ge=7, le=60),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
) -> dict:
    """Project what would have happened if this recommendation were applied N days ago.

    Replays the recommendation against historical daily snapshots
    and returns projected ACOS, spend, sales, and confidence intervals.
    """
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)

    recommendation = monitoring_repository.get_recommendation(
        workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    if recommendation is None:
        raise ApiError(code="RECOMMENDATION_NOT_FOUND", message="Recommendation not found.", status_code=404)

    # Fetch daily snapshots for this campaign/search term
    # In production, query daily_monitoring_snapshots table
    daily_snaps: list[dict] = []
    try:
        daily_snaps = monitoring_repository.list_daily_snapshots(
            workspace_id=workspace_id,
            product_id=recommendation.product_id,
            campaign_name=recommendation.campaign_name,
            limit=window_days,
        )
    except Exception:
        daily_snaps = []  # graceful degradation — backtest works even without daily data

    result = project_recommendation_impact(
        recommendation=recommendation,
        daily_snapshots=daily_snaps,
        window_days=window_days,
    )
    result["workspace_id"] = str(workspace_id)
    return success_response(data=result)


# ── Planner Agent ────────────────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/planner/evaluate")
def evaluate_planner(
    workspace_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    data_quality_score: float = Query(default=1.0, ge=0.0, le=1.0),
    strategy_mode: str = Query(default="profit"),
    total_rows: int = Query(default=0, ge=0),
    search_term_count: int = Query(default=0, ge=0),
    campaign_count: int = Query(default=0, ge=0),
    wasteful_term_count: int = Query(default=0, ge=0),
) -> dict:
    """Run the planner agent to determine which downstream agents should execute.

    Returns RUN/SKIP/LIGHT decisions for each optimization agent
    with reasoning and skip explanations.
    """
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)

    # Build synthetic grouped_entities for the planner
    entities: dict[str, dict] = {}
    for i in range(search_term_count):
        is_wasteful = i < wasteful_term_count
        entities[f"st_{i}"] = {
            "entity_type": "search_term",
            "metrics": {"spend": 10 if is_wasteful else 5, "orders": 0 if is_wasteful else 1},
        }
    for i in range(campaign_count):
        entities[f"camp_{i}"] = {"entity_type": "campaign", "metrics": {}}

    plan = plan_agent_execution(
        data_quality_report={"overall_score": data_quality_score},
        strategy_mode=strategy_mode,
        grouped_entities=entities,
        total_rows=total_rows,
    )

    return success_response(data={
        "strategy_mode": plan.strategy_mode,
        "data_quality_score": plan.data_quality_score,
        "total_rows": plan.total_rows,
        "bid_optimization": plan.bid_optimization.value,
        "negative_keyword": plan.negative_keyword.value,
        "budget_reallocation": plan.budget_reallocation.value,
        "campaign_structure": plan.campaign_structure.value,
        "skip_reasons": plan.skip_reasons,
        "reasoning": plan.reasoning,
        "warnings": plan.warnings,
    })


# ── Statistical Significance Check ───────────────────────────────────────

@router.post("/workspaces/{workspace_id}/recommendations/{recommendation_id}/significance")
def check_significance(
    workspace_id: UUID,
    recommendation_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
) -> dict:
    """Run Wilson lower-bound statistical significance checks on a recommendation.

    Returns pass/fail for each check: minimum clicks, minimum spend,
    Wilson CVR lower bound, negative keyword waste evidence, pause evidence.
    """
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)

    recommendation = monitoring_repository.get_recommendation(
        workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    if recommendation is None:
        raise ApiError(code="RECOMMENDATION_NOT_FOUND", message="Recommendation not found.", status_code=404)

    metrics = recommendation.input_metrics_json
    report = evaluate_recommendation_significance(
        clicks=int(metrics.get("clicks", 0)),
        orders=int(metrics.get("orders", 0)),
        impressions=int(metrics.get("impressions", 0)),
        spend=float(metrics.get("spend", 0) or 0),
        recommendation_type=str(recommendation.recommendation_type.value),
    )

    return success_response(data={
        "recommendation_id": str(recommendation.id),
        "recommendation_type": str(recommendation.recommendation_type.value),
        "overall_passed": report.overall_passed,
        "requires_more_data": report.requires_more_data,
        "wilson_cvr_lower": report.wilson_cvr_lower,
        "wilson_cvr_upper": report.wilson_cvr_upper,
        "minimum_clicks_met": report.minimum_clicks_met,
        "minimum_spend_met": report.minimum_spend_met,
        "minimum_orders_met": report.minimum_orders_met,
        "errors": report.errors,
        "warnings": report.warnings,
        "checks": [
            {"name": c.name, "passed": c.passed, "value": c.value, "threshold": c.threshold, "detail": c.detail, "is_warning": c.is_warning}
            for c in report.checks
        ],
    })


# ── Rule Calibration ─────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/calibration/status")
def get_calibration_status(
    workspace_id: UUID,
    rule_name: str | None = Query(default=None),
    parameter: str | None = Query(default=None),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    """Get current calibration state for rule parameters.

    Returns original and current calibrated values for all params,
    or filtered by rule_name/parameter.
    """
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)

    from apps.api.app.services.rule_calibration import CALIBRATABLE_PARAMETERS

    params = []
    for p in CALIBRATABLE_PARAMETERS:
        if rule_name and p.rule_name != rule_name:
            continue
        if parameter and p.parameter != parameter:
            continue
        params.append({
            "rule_name": p.rule_name,
            "parameter": p.parameter,
            "original_value": p.original_value,
            "bounded_min": p.bounded_min,
            "bounded_max": p.bounded_max,
            "description": p.description,
        })

    return success_response(data={
        "workspace_id": str(workspace_id),
        "total_parameters": len(params),
        "parameters": params,
    })