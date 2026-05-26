from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from uuid import UUID, uuid4

from apps.api.app.core.errors import ApiError
from apps.api.app.domain.monitoring import AGENT_SCHEMA_VERSION, MONITORING_RULE_VERSION, SP_SEARCH_TERM_REQUIRED_COLUMNS
from apps.api.app.schemas.monitoring import (
    AiRun,
    MonitoringImport,
    MonitoringSnapshot,
    Recommendation,
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)
from apps.api.app.schemas.product_profiles import ProductProfile
from apps.api.app.schemas.upload_parsing import ParsedUploadRow


def normalize_sp_search_term_rows(*, import_record: MonitoringImport, rows: list[ParsedUploadRow]) -> tuple[list[MonitoringSnapshot], list[dict]]:
    if not rows:
        raise ApiError(code="MONITORING_IMPORT_EMPTY", message="Monitoring import requires parsed rows.", status_code=409)
    available = {_normalize_column(column) for column in rows[0].row_data_json}
    missing = sorted(SP_SEARCH_TERM_REQUIRED_COLUMNS - available)
    if missing:
        raise ApiError(
            code="MONITORING_REPORT_COLUMNS_MISSING",
            message="Sponsored Products Search Term report is missing required columns.",
            status_code=400,
            details={"missing_columns": missing},
        )

    warnings: list[dict] = []
    snapshots: list[MonitoringSnapshot] = []
    now = datetime.now(UTC)
    for row in rows:
        data = {_normalize_column(key): value for key, value in row.row_data_json.items()}
        try:
            snapshots.append(
                MonitoringSnapshot(
                    id=uuid4(),
                    workspace_id=import_record.workspace_id,
                    product_id=import_record.product_id,
                    monitoring_import_id=import_record.id,
                    upload_id=import_record.upload_id,
                    parse_run_id=import_record.parse_run_id,
                    source_row_id=row.id,
                    campaign_name=_required_text(data, "campaign name"),
                    ad_group_name=_required_text(data, "ad group name"),
                    targeting=_required_text(data, "targeting"),
                    match_type=_optional_text(data, "match type"),
                    customer_search_term=_required_text(data, "customer search term"),
                    start_date=_optional_text(data, "start date"),
                    end_date=_optional_text(data, "end date"),
                    impressions=_int(data.get("impressions")),
                    clicks=_int(data.get("clicks")),
                    spend=_decimal(data.get("spend")),
                    sales=_decimal(data.get("7 day total sales")),
                    orders=_int(data.get("7 day total orders")),
                    units=_int_or_none(data.get("7 day total units")),
                    cpc=_decimal_or_none(data.get("cost per click cpc")),
                    ctr=_decimal_or_none(data.get("click thru rate ctr") if "click thru rate ctr" in data else data.get("clickthru rate ctr")),
                    cvr=_decimal_or_none(data.get("7 day conversion rate")),
                    acos=_decimal_or_none(data.get("total advertising cost of sales acos")),
                    roas=_decimal_or_none(data.get("total return on advertising spend roas")),
                    raw_metrics_json=row.row_data_json,
                    created_at=now,
                )
            )
        except ValueError as exc:
            warnings.append({"row_number": row.row_number, "code": "ROW_NORMALIZATION_SKIPPED", "message": str(exc)})
    return snapshots, warnings


def build_recommendations(*, product: ProductProfile, import_record: MonitoringImport, snapshots: list[MonitoringSnapshot]) -> list[Recommendation]:
    target_acos = _decimal(product.target_acos)
    default_budget = _decimal(product.default_budget)
    now = datetime.now(UTC)
    recommendations: list[Recommendation] = []
    for snapshot in snapshots:
        recommendation_type, priority, rule_name, proposed = _recommendation_for(snapshot=snapshot, target_acos=target_acos, default_budget=default_budget)
        if recommendation_type is None:
            continue
        metrics = _metrics_json(snapshot)
        recommendations.append(
            Recommendation(
                id=uuid4(),
                workspace_id=import_record.workspace_id,
                product_id=import_record.product_id,
                monitoring_import_id=import_record.id,
                snapshot_id=snapshot.id,
                recommendation_type=recommendation_type,
                status=RecommendationStatus.PENDING_APPROVAL,
                priority=priority,
                rule_version_id=MONITORING_RULE_VERSION,
                rule_name=rule_name,
                campaign_name=snapshot.campaign_name,
                ad_group_name=snapshot.ad_group_name,
                targeting=snapshot.targeting,
                customer_search_term=snapshot.customer_search_term,
                input_metrics_json=metrics,
                proposed_action_json=proposed,
                explanation_json=explain_recommendation(recommendation_type=recommendation_type, priority=priority, metrics=metrics, proposed_action=proposed),
                created_at=now,
                updated_at=now,
            )
        )
    return recommendations


def build_stakeholder_ai_run(*, workspace_id: UUID, recommendations: list[Recommendation], snapshots: list[MonitoringSnapshot]) -> AiRun:
    counts: dict[str, int] = {}
    for recommendation in recommendations:
        counts[recommendation.recommendation_type.value] = counts.get(recommendation.recommendation_type.value, 0) + 1
    spend = sum((snapshot.spend for snapshot in snapshots), Decimal("0"))
    sales = sum((snapshot.sales for snapshot in snapshots), Decimal("0"))
    orders = sum(snapshot.orders for snapshot in snapshots)
    summary = {
        "headline": f"{len(recommendations)} recommendations need human review before any ad change.",
        "recommendation_counts": counts,
        "total_spend": str(spend),
        "total_sales": str(sales),
        "total_orders": orders,
        "stakeholder_note": "Agents summarized rule-backed evidence only. No bid, pause, removal, or negative keyword change has been executed.",
        "next_step": "Review high-priority recommendations and approve or reject with notes.",
    }
    payload = json.dumps({"counts": counts, "spend": str(spend), "sales": str(sales), "orders": orders}, sort_keys=True)
    now = datetime.now(UTC)
    return AiRun(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_name="stakeholder_reporting_agent",
        provider="local-rule-explainer",
        model="deterministic-v1",
        schema_version=AGENT_SCHEMA_VERSION,
        input_hash=sha256(payload.encode("utf-8")).hexdigest(),
        output_json=summary,
        status="succeeded",
        latency_ms=0,
        created_at=now,
    )


def explain_recommendation(*, recommendation_type: RecommendationType, priority: RecommendationPriority, metrics: dict, proposed_action: dict) -> dict:
    labels = {
        RecommendationType.INCREASE_BID: "Low traffic suggests a cautious bid increase may help gather data.",
        RecommendationType.DECREASE_BID: "Efficiency is weak enough to review a bid decrease.",
        RecommendationType.PAUSE_REVIEW: "Spend or clicks are high with no sales, so a pause review is recommended.",
        RecommendationType.NEGATIVE_KEYWORD_REVIEW: "The search term is consuming spend without orders and should be reviewed as a negative.",
        RecommendationType.WATCH_LOCK: "Performance is efficient; avoid aggressive changes and keep watching.",
    }
    return {
        "agent_name": _agent_for_type(recommendation_type),
        "summary": labels[recommendation_type],
        "priority": priority.value,
        "evidence": metrics,
        "proposed_action": proposed_action,
        "approval_required": True,
        "execution_boundary": "recommendation_only_no_live_amazon_change",
    }


def _recommendation_for(*, snapshot: MonitoringSnapshot, target_acos: Decimal, default_budget: Decimal):
    high_spend = max(default_budget * Decimal("2"), Decimal("20"))
    if snapshot.spend >= high_spend and snapshot.orders == 0:
        return RecommendationType.PAUSE_REVIEW, RecommendationPriority.HIGH, "high_spend_no_sales_pause_review", _action("pause_review", snapshot, None)
    if snapshot.clicks >= 10 and snapshot.orders == 0:
        return RecommendationType.NEGATIVE_KEYWORD_REVIEW, RecommendationPriority.HIGH, "click_waste_negative_keyword_review", _action("negative_keyword_review", snapshot, None)
    if snapshot.sales > 0 and snapshot.acos is not None and snapshot.acos > target_acos * Decimal("1.25"):
        return RecommendationType.DECREASE_BID, RecommendationPriority.MEDIUM, "acos_above_target_decrease_bid", _action("decrease_bid", snapshot, Decimal("0.90"))
    if snapshot.sales > 0 and snapshot.acos is not None and snapshot.acos <= target_acos * Decimal("0.80"):
        return RecommendationType.WATCH_LOCK, RecommendationPriority.LOW, "efficient_acos_watch_lock", _action("watch_lock", snapshot, None)
    if snapshot.impressions >= 10 and snapshot.clicks < 3 and snapshot.spend <= Decimal("5"):
        return RecommendationType.INCREASE_BID, RecommendationPriority.MEDIUM, "low_traffic_low_spend_increase_bid", _action("increase_bid", snapshot, Decimal("1.10"))
    return None, None, None, None


def _action(action: str, snapshot: MonitoringSnapshot, bid_multiplier: Decimal | None) -> dict:
    return {
        "action": action,
        "action_level": "targeting",
        "campaign_name": snapshot.campaign_name,
        "ad_group_name": snapshot.ad_group_name,
        "targeting": snapshot.targeting,
        "customer_search_term": snapshot.customer_search_term,
        "suggested_bid_multiplier": str(bid_multiplier) if bid_multiplier is not None else None,
        "requires_human_approval": True,
        "requires_console_or_bulk_sheet_lookup": action in {"increase_bid", "decrease_bid"},
    }


def _metrics_json(snapshot: MonitoringSnapshot) -> dict:
    return {
        "impressions": snapshot.impressions,
        "clicks": snapshot.clicks,
        "spend": str(snapshot.spend),
        "sales": str(snapshot.sales),
        "orders": snapshot.orders,
        "acos": str(snapshot.acos) if snapshot.acos is not None else None,
        "roas": str(snapshot.roas) if snapshot.roas is not None else None,
        "ctr": str(snapshot.ctr) if snapshot.ctr is not None else None,
        "cvr": str(snapshot.cvr) if snapshot.cvr is not None else None,
    }


def _agent_for_type(recommendation_type: RecommendationType) -> str:
    if recommendation_type in {RecommendationType.INCREASE_BID, RecommendationType.DECREASE_BID, RecommendationType.WATCH_LOCK}:
        return "bid_optimization_agent"
    if recommendation_type == RecommendationType.NEGATIVE_KEYWORD_REVIEW:
        return "negative_keyword_agent"
    return "pause_review_agent"


def _normalize_column(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()
    return normalized.replace("  ", " ")


def _required_text(data: dict, key: str) -> str:
    value = _optional_text(data, key)
    if not value:
        raise ValueError(f"Missing required value for {key}.")
    return value


def _optional_text(data: dict, key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value) -> int:
    if value is None or value == "":
        return 0
    return int(Decimal(str(value)))


def _int_or_none(value) -> int | None:
    return None if value is None or value == "" else _int(value)


def _decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value {value}.") from exc


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return _decimal(value)
