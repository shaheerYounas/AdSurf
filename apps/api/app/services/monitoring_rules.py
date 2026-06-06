from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from uuid import UUID, uuid4

from apps.api.app.core.errors import ApiError
from apps.api.app.domain.monitoring import (
    AGENT_SCHEMA_VERSION,
    MONITORING_EVIDENCE_SCHEMA_VERSION,
    MONITORING_RULE_VERSION,
    SP_SEARCH_TERM_ORDERS_ALIASES,
    SP_SEARCH_TERM_REQUIRED_COLUMNS,
    SP_SEARCH_TERM_SALES_ALIASES,
)
from apps.api.app.schemas.monitoring import (
    AiRun,
    MonitoringImport,
    MonitoringSnapshot,
    Recommendation,
    RecommendationConfidence,
    RecommendationEntityType,
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)
from apps.api.app.schemas.product_profiles import ProductProfile
from apps.api.app.schemas.upload_parsing import ParsedUploadRow
from apps.api.app.services import monitoring_metrics
from apps.api.app.services.amazon_ads_safeguards import analyze_search_term_report_rows
from apps.api.app.services.report_type_detector import ReportTypeDetector


MONEY_QUANT = Decimal("0.0001")
RATE_QUANT = Decimal("0.0001")
SP_SEARCH_TERM_COLUMN_ALIASES = {
    # Both 7-day and 14-day attribution windows are treated identically.
    # Amazon exports either depending on the account's attribution setting.
    "7 day total sales": sorted(SP_SEARCH_TERM_SALES_ALIASES - {"7 day total sales"}),
    "7 day total orders": sorted(SP_SEARCH_TERM_ORDERS_ALIASES - {"7 day total orders"}),
    "7 day total units": ["units", "units #", "7 day total units #", "7 day total units number",
                          "14 day total units", "14 day total units #", "14 day total units number"],
    "click thru rate ctr": ["clickthru rate ctr"],
}
DATA_QUALITY_CRITICAL_FLAGS = {"clicks_exceed_impressions", "orders_exceed_clicks", "negative_metric_value", "missing_campaign_name", "missing_search_term"}
RATE_TOLERANCE = Decimal("0.0200")
ROAS_TOLERANCE = Decimal("0.1000")
MIN_BID = Decimal("0.1000")
MAX_BID_INCREASE_MULTIPLIER = Decimal("1.3000")
MAX_BID_DECREASE_MULTIPLIER = Decimal("0.6000")
ASIN_PATTERN = re.compile(r"^b[0-9a-z]{9}$", re.IGNORECASE)


def normalize_sp_search_term_rows(*, import_record: MonitoringImport, rows: list[ParsedUploadRow]) -> tuple[list[MonitoringSnapshot], list[dict]]:
    if not rows:
        raise ApiError(code="MONITORING_IMPORT_EMPTY", message="Monitoring import requires parsed rows.", status_code=409)
    available = {_normalize_column(column) for column in rows[0].row_data_json}
    for canonical, variants in SP_SEARCH_TERM_COLUMN_ALIASES.items():
        if canonical in available:
            continue
        if any(variant in available for variant in variants):
            available.add(canonical)
    missing = sorted(SP_SEARCH_TERM_REQUIRED_COLUMNS - available)
    if missing:
        raise ApiError(
            code="MONITORING_REPORT_COLUMNS_MISSING",
            message="Sponsored Products Search Term report is missing required columns.",
            status_code=400,
            details={"missing_columns": missing},
        )

    warnings: list[dict] = []
    detection = ReportTypeDetector().detect(headers=rows[0].row_data_json.keys(), sample_rows=[row.row_data_json for row in rows[:25]])
    safeguard_rows = [{**row.row_data_json, "_row_number": row.row_number} for row in rows]
    warnings.extend(analyze_search_term_report_rows(rows=safeguard_rows, detection=detection).warnings)
    warnings.extend(_product_detection_messages(rows))
    snapshots: list[MonitoringSnapshot] = []
    now = datetime.now(UTC)
    for row in rows:
        data = _canonical_row_data(row.row_data_json)
        try:
            impressions = _int(data.get("impressions"))
            clicks = _int(data.get("clicks"))
            spend = _money(data.get("spend"))
            sales = _money(data.get("7 day total sales"))
            orders = _int(data.get("7 day total orders"))
            units = _int_or_none(data.get("7 day total units"))
            cpc = _rate_or_money(data.get("cost per click cpc")) or _safe_divide(spend, Decimal(clicks), MONEY_QUANT)
            ctr = _rate(data.get("click thru rate ctr") if "click thru rate ctr" in data else data.get("clickthru rate ctr")) or _safe_divide(Decimal(clicks), Decimal(impressions), RATE_QUANT)
            cvr = _rate(data.get("7 day conversion rate")) or _safe_divide(Decimal(orders), Decimal(clicks), RATE_QUANT)
            acos = _rate(data.get("total advertising cost of sales acos")) if sales > 0 else None
            if sales > 0:
                acos = _safe_divide(spend, sales, RATE_QUANT) if acos is None else acos
            roas = _rate_or_money(data.get("total return on advertising spend roas")) or _safe_divide(sales, spend, RATE_QUANT)
            snapshots.append(
                MonitoringSnapshot(
                    id=uuid4(),
                    workspace_id=import_record.workspace_id,
                    product_id=import_record.product_id,
                    monitoring_import_id=import_record.id,
                    upload_id=import_record.upload_id,
                    parse_run_id=import_record.parse_run_id,
                    source_row_id=row.id or uuid4(),
                    campaign_name=_required_text(data, "campaign name"),
                    ad_group_name=_required_text(data, "ad group name"),
                    targeting=_required_text(data, "targeting"),
                    match_type=_optional_text(data, "match type"),
                    customer_search_term=_required_text(data, "customer search term"),
                    start_date=_optional_text(data, "start date"),
                    end_date=_optional_text(data, "end date"),
                    impressions=impressions,
                    clicks=clicks,
                    spend=spend,
                    sales=sales,
                    orders=orders,
                    units=units,
                    cpc=cpc,
                    ctr=ctr,
                    cvr=cvr,
                    acos=acos,
                    roas=roas,
                    raw_metrics_json=row.row_data_json,
                    created_at=now,
                )
            )
        except ValueError as exc:
            warnings.append({"row_number": row.row_number, "code": "ROW_NORMALIZATION_SKIPPED", "message": str(exc), "severity": "error"})
    return snapshots, warnings


def build_recommendations(*, product: ProductProfile, import_record: MonitoringImport, snapshots: list[MonitoringSnapshot]) -> list[Recommendation]:
    target_acos = _money(product.target_acos)
    default_budget = _money(product.default_budget)
    default_bid = _money(product.default_bid)
    rollups = monitoring_metrics.build_performance_rollups(snapshots)
    now = datetime.now(UTC)
    recommendations: list[Recommendation] = []
    for snapshot in snapshots:
        rule_result = _recommendation_for(snapshot=snapshot, target_acos=target_acos, default_budget=default_budget, default_bid=default_bid)
        metrics = monitoring_metrics.snapshot_metrics(snapshot, report_performance=rollups["report"])
        evidence = _evidence_json(
            snapshot=snapshot,
            metrics=metrics,
            rule_result=rule_result,
            rollups=rollups,
            target_acos=target_acos,
            default_budget=default_budget,
        )
        action = rule_result["proposed_action"]
        _recommended_bid_str = action.get("recommended_bid")
        _current_bid_str = action.get("current_bid")
        _change_pct_str = action.get("change_percent")
        recommendations.append(
            Recommendation(
                id=uuid4(),
                workspace_id=import_record.workspace_id,
                product_id=import_record.product_id,
                monitoring_import_id=import_record.id,
                snapshot_id=snapshot.id,
                recommendation_type=rule_result["recommendation_type"],
                entity_type=rule_result["entity_type"],
                status=RecommendationStatus.PENDING_APPROVAL,
                priority=rule_result["priority"],
                confidence=rule_result["confidence"],
                rule_version_id=MONITORING_RULE_VERSION,
                rule_name=rule_result["rule_name"],
                campaign_name=snapshot.campaign_name,
                ad_group_name=snapshot.ad_group_name,
                targeting=snapshot.targeting,
                customer_search_term=snapshot.customer_search_term,
                match_type=snapshot.match_type,
                current_bid=Decimal(_current_bid_str) if _current_bid_str else None,
                recommended_bid=Decimal(_recommended_bid_str) if _recommended_bid_str else None,
                change_percent=Decimal(_change_pct_str) if _change_pct_str else None,
                input_metrics_json=metrics,
                current_metric_snapshot_json=metrics,
                evidence_json=evidence,
                proposed_action_json=action,
                explanation_json=explain_recommendation(
                    recommendation_type=rule_result["recommendation_type"],
                    priority=rule_result["priority"],
                    evidence=evidence,
                    proposed_action=action,
                ),
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
    clicks = sum(snapshot.clicks for snapshot in snapshots)
    zero_order_spend = sum((snapshot.spend for snapshot in snapshots if snapshot.orders == 0), Decimal("0"))
    actionable = sum(1 for item in recommendations if item.recommendation_type in {RecommendationType.INCREASE_BID, RecommendationType.DECREASE_BID, RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE, RecommendationType.MOVE_TO_EXACT, RecommendationType.PAUSE_REVIEW})
    watch = sum(1 for item in recommendations if item.recommendation_type in {RecommendationType.KEEP_RUNNING, RecommendationType.WATCH_LOCK})
    data_quality = counts.get(RecommendationType.DATA_QUALITY_REVIEW.value, 0)
    budget = counts.get(RecommendationType.BUDGET_REVIEW.value, 0)
    acos = _safe_divide(spend, sales, RATE_QUANT) if sales > 0 else None
    summary = {
        "headline": f"{len(snapshots)} report rows analyzed. {len(recommendations)} recommendations generated for human review.",
        "recommendation_counts": counts,
        "actionable_recommendations": actionable,
        "watch_insights": watch,
        "data_quality_checks": data_quality,
        "budget_review_notes": budget,
        "total_spend": str(spend.quantize(MONEY_QUANT)),
        "total_sales": str(sales.quantize(MONEY_QUANT)),
        "total_orders": orders,
        "total_clicks": clicks,
        "account_acos": str(acos) if acos is not None else None,
        "zero_order_spend": str(zero_order_spend.quantize(MONEY_QUANT)),
        "stakeholder_note": "Deterministic rules generated output-only recommendations. No AI final decision, bid change, pause, negative keyword, export, or Amazon Ads mutation has been executed.",
        "next_step": "Review pending recommendations and approve or reject with notes.",
    }
    payload = json.dumps({"counts": counts, "spend": str(spend), "sales": str(sales), "orders": orders}, sort_keys=True)
    now = datetime.now(UTC)
    return AiRun(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_name="stakeholder_reporting_agent",
        provider="local-deterministic-rules",
        model="monitoring-rules-v2",
        schema_version=AGENT_SCHEMA_VERSION,
        input_hash=sha256(payload.encode("utf-8")).hexdigest(),
        output_json=summary,
        status="succeeded",
        latency_ms=0,
        created_at=now,
    )


def explain_recommendation(*, recommendation_type: RecommendationType, priority: RecommendationPriority, evidence: dict, proposed_action: dict) -> dict:
    labels = {
        RecommendationType.KEEP_RUNNING: "Performance is within the current rule thresholds; keep monitoring without changing ads.",
        RecommendationType.INCREASE_BID: "This search term has multiple orders below target ACOS, so a bounded bid increase can be reviewed.",
        RecommendationType.DECREASE_BID: "This target has orders, but ACOS is materially above the product target with enough evidence to review a bid decrease.",
        RecommendationType.PAUSE_REVIEW: "Spend and clicks are high with no orders, so a human should review whether the target should be paused.",
        RecommendationType.ADD_NEGATIVE_EXACT: "This search term has meaningful spend or click volume with no orders. Review it as a negative exact.",
        RecommendationType.ADD_NEGATIVE_PHRASE: "A broad or phrase match pattern has meaningful spend/click volume with no orders. Review it as a negative phrase.",
        RecommendationType.MOVE_TO_EXACT: "This non-exact search term converted efficiently and can be reviewed for exact targeting.",
        RecommendationType.WATCH_LOCK: "Performance is efficient enough to avoid aggressive optimization and keep watching.",
        RecommendationType.DATA_QUALITY_REVIEW: "This row needs review because reported metrics do not match expected Amazon Ads calculations or required context.",
        RecommendationType.BUDGET_REVIEW: "Performance is promising but spend suggests budget pressure should be reviewed.",
        RecommendationType.LEGACY_NEGATIVE_KEYWORD_REVIEW: "The search term should be reviewed as a negative keyword.",
    }
    metrics = evidence.get("snapshot_metrics", {})
    advanced_details = {
        "rule": evidence["rule_evaluation"]["rule_name"],
        "thresholds": evidence.get("thresholds", {}),
        "source": "deterministic_rules_v1",
        "metric_snapshot": metrics,
    }
    return {
        "summary": labels[recommendation_type],
        "why_flagged": labels[recommendation_type],
        "evidence": _plain_evidence(metrics),
        "recommended_action": proposed_action.get("action"),
        "risk": _risk_note(recommendation_type, priority),
        "approval_note": "Human approval is required. No live Amazon Ads change has been made.",
        "priority": priority.value,
        "confidence": evidence["rule_evaluation"]["confidence"],
        "evidence_schema_version": evidence["schema_version"],
        "advanced_details": advanced_details,
        "proposed_action": proposed_action,
        "approval_required": True,
        "decision_source": "deterministic_rules",
        "ai_final_decision": False,
        "execution_boundary": "recommendation_only_no_live_amazon_change",
    }


def _plain_evidence(metrics: dict) -> str:
    spend = metrics.get("spend", "0")
    clicks = metrics.get("clicks", 0)
    orders = metrics.get("orders", 0)
    sales = metrics.get("sales", "0")
    return f"Spend {spend}, clicks {clicks}, orders {orders}, sales {sales}."


def _risk_note(recommendation_type: RecommendationType, priority: RecommendationPriority) -> str:
    if recommendation_type in {RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE}:
        return "Medium - the term may still be relevant, so approve only after reviewing product fit."
    if recommendation_type in {RecommendationType.INCREASE_BID, RecommendationType.DECREASE_BID}:
        return "Medium - bid changes affect spend and require manual approval/export."
    if recommendation_type == RecommendationType.DATA_QUALITY_REVIEW:
        return "High" if priority == RecommendationPriority.CRITICAL else "Medium"
    return priority.value


def _recommendation_for(*, snapshot: MonitoringSnapshot, target_acos: Decimal, default_budget: Decimal, default_bid: Decimal) -> dict:
    high_spend = max(default_budget * Decimal("2"), Decimal("20"))
    quality_flags = _data_quality_flags(snapshot)
    metrics = monitoring_metrics.snapshot_metrics(snapshot)
    signals = monitoring_metrics.condition_signals(snapshot, target_acos=target_acos, default_budget=default_budget)
    if quality_flags:
        critical = any(flag in DATA_QUALITY_CRITICAL_FLAGS for flag in quality_flags)
        return _rule(
            RecommendationType.DATA_QUALITY_REVIEW,
            RecommendationPriority.CRITICAL if critical else RecommendationPriority.MEDIUM,
            "inconsistent_metrics_data_quality_review",
            _action("data_quality_review", snapshot, None, flags=quality_flags),
            confidence=RecommendationConfidence.HIGH if critical else RecommendationConfidence.MEDIUM,
        )
    if snapshot.spend >= high_spend and snapshot.orders == 0 and snapshot.clicks >= 15:
        return _rule(
            RecommendationType.PAUSE_REVIEW,
            RecommendationPriority.CRITICAL,
            "high_spend_no_orders_pause_review",
            _action("pause_review", snapshot, None),
            entity_type=RecommendationEntityType.TARGET,
            confidence=RecommendationConfidence.HIGH,
        )
    if _should_add_negative_phrase(snapshot=snapshot, default_budget=default_budget):
        return _rule(
            RecommendationType.ADD_NEGATIVE_PHRASE,
            RecommendationPriority.HIGH,
            "broad_waste_no_orders_add_negative_phrase",
            _action("add_negative_phrase", snapshot, None, negative_match_type="phrase"),
            confidence=RecommendationConfidence.HIGH,
        )
    if _should_add_negative_exact(snapshot):
        return _rule(
            RecommendationType.ADD_NEGATIVE_EXACT,
            RecommendationPriority.HIGH,
            "search_term_waste_no_orders_add_negative_exact",
            _action("add_negative_exact", snapshot, None, negative_match_type="exact"),
            confidence=RecommendationConfidence.HIGH if snapshot.clicks >= 30 or snapshot.spend >= Decimal("20") else RecommendationConfidence.MEDIUM,
        )
    if _should_decrease_bid(snapshot=snapshot, target_acos=target_acos):
        multiplier = _bounded_bid_multiplier(target_acos / snapshot.acos, minimum=MAX_BID_DECREASE_MULTIPLIER, maximum=Decimal("1.0000")) if snapshot.acos else Decimal("0.9000")
        return _rule(
            RecommendationType.DECREASE_BID,
            RecommendationPriority.MEDIUM,
            "acos_above_target_decrease_bid",
            _action("decrease_bid", snapshot, multiplier, current_bid=default_bid),
            entity_type=RecommendationEntityType.TARGET,
            confidence=RecommendationConfidence.HIGH if snapshot.clicks >= 15 or snapshot.spend >= Decimal("20") else RecommendationConfidence.MEDIUM,
        )
    if signals["budget_pressure"]:
        return _rule(
            RecommendationType.BUDGET_REVIEW,
            RecommendationPriority.MEDIUM,
            "strong_performance_budget_pressure_review",
            _action("budget_review", snapshot, None),
            entity_type=RecommendationEntityType.CAMPAIGN,
            confidence=RecommendationConfidence.MEDIUM,
        )
    if _should_move_to_exact(snapshot=snapshot, target_acos=target_acos):
        return _rule(
            RecommendationType.MOVE_TO_EXACT,
            RecommendationPriority.MEDIUM,
            "efficient_non_exact_search_term_move_to_exact",
            _action("move_to_exact", snapshot, None),
            confidence=RecommendationConfidence.HIGH,
        )
    if _should_increase_bid(snapshot=snapshot, target_acos=target_acos):
        multiplier = _bounded_bid_multiplier(target_acos / snapshot.acos, minimum=Decimal("1.0500"), maximum=MAX_BID_INCREASE_MULTIPLIER) if snapshot.acos else Decimal("1.1000")
        return _rule(
            RecommendationType.INCREASE_BID,
            RecommendationPriority.MEDIUM,
            "strong_conversion_low_impressions_increase_bid",
            _action("increase_bid", snapshot, multiplier, current_bid=default_bid),
            entity_type=RecommendationEntityType.TARGET,
            confidence=RecommendationConfidence.HIGH if snapshot.orders >= 3 else RecommendationConfidence.MEDIUM,
        )
    if _has_sales(snapshot) and snapshot.acos is not None and snapshot.acos <= target_acos * Decimal("0.80") and snapshot.orders >= 2:
        return _rule(
            RecommendationType.WATCH_LOCK,
            RecommendationPriority.LOW,
            "efficient_acos_watch_lock",
            _action("watch_lock", snapshot, None),
            confidence=RecommendationConfidence.MEDIUM,
        )
    if snapshot.orders == 0 and snapshot.clicks >= 10:
        return _rule(
            RecommendationType.WATCH_LOCK,
            RecommendationPriority.LOW,
            "weak_zero_order_signal_watch_lock",
            _action("watch_lock", snapshot, None),
            confidence=RecommendationConfidence.LOW,
        )
    if signals["under_tested"]:
        return _rule(
            RecommendationType.WATCH_LOCK,
            RecommendationPriority.LOW,
            "under_tested_watch_lock",
            _action("watch_lock", snapshot, None),
            confidence=RecommendationConfidence.LOW,
        )
    return _rule(
        RecommendationType.KEEP_RUNNING,
        RecommendationPriority.LOW,
        "within_thresholds_keep_running",
        _action("keep_running", snapshot, None),
        confidence=RecommendationConfidence.MEDIUM if metrics["clicks"] else RecommendationConfidence.LOW,
    )


def _rule(
    recommendation_type: RecommendationType,
    priority: RecommendationPriority,
    rule_name: str,
    proposed_action: dict,
    *,
    entity_type: RecommendationEntityType = RecommendationEntityType.SEARCH_TERM,
    confidence: RecommendationConfidence = RecommendationConfidence.MEDIUM,
) -> dict:
    return {
        "recommendation_type": recommendation_type,
        "entity_type": entity_type,
        "priority": priority,
        "confidence": confidence,
        "rule_name": rule_name,
        "proposed_action": proposed_action,
    }


def _action(
    action: str,
    snapshot: MonitoringSnapshot,
    bid_multiplier: Decimal | None,
    *,
    negative_match_type: str | None = None,
    flags: list[str] | None = None,
    current_bid: Decimal | None = None,
) -> dict:
    recommended_bid = _recommended_bid(current_bid=current_bid, multiplier=bid_multiplier)
    change_percent = ((bid_multiplier - Decimal("1")) * Decimal("100")).quantize(Decimal("0.01")) if bid_multiplier is not None else None
    return {
        "action": action,
        "action_level": "search_term" if action.startswith("add_negative") or action == "move_to_exact" else "targeting",
        "campaign_name": snapshot.campaign_name,
        "ad_group_name": snapshot.ad_group_name,
        "targeting": snapshot.targeting,
        "customer_search_term": snapshot.customer_search_term,
        "suggested_bid_multiplier": str(bid_multiplier) if bid_multiplier is not None else None,
        "current_bid": str(current_bid) if current_bid is not None else None,
        "recommended_bid": str(recommended_bid) if recommended_bid is not None else None,
        "change_percent": str(change_percent) if change_percent is not None else None,
        "safety_bounds": {
            "max_increase_pct": "30",
            "max_decrease_pct": "40",
            "minimum_bid": str(MIN_BID),
        }
        if bid_multiplier is not None
        else None,
        "negative_match_type": negative_match_type,
        "data_quality_flags": flags or [],
        "requires_human_approval": True,
        "requires_console_or_bulk_sheet_lookup": action in {"increase_bid", "decrease_bid", "pause_review", "add_negative_exact", "add_negative_phrase", "move_to_exact", "budget_review"},
        "executes_live_amazon_change": False,
    }


def _metrics_json(snapshot: MonitoringSnapshot) -> dict:
    return {
        "impressions": snapshot.impressions,
        "clicks": snapshot.clicks,
        "spend": str(snapshot.spend),
        "sales": str(snapshot.sales),
        "orders": snapshot.orders,
        "units": snapshot.units,
        "cpc": str(snapshot.cpc) if snapshot.cpc is not None else None,
        "acos": str(snapshot.acos) if snapshot.acos is not None else None,
        "roas": str(snapshot.roas) if snapshot.roas is not None else None,
        "ctr": str(snapshot.ctr) if snapshot.ctr is not None else None,
        "cvr": str(snapshot.cvr) if snapshot.cvr is not None else None,
    }


def _evidence_json(
    *,
    snapshot: MonitoringSnapshot,
    metrics: dict,
    rule_result: dict,
    rollups: dict,
    target_acos: Decimal,
    default_budget: Decimal,
) -> dict:
    return {
        "schema_version": MONITORING_EVIDENCE_SCHEMA_VERSION,
        "performance_grain": "search_term",
        "rule_evaluation": {
            "rule_version_id": MONITORING_RULE_VERSION,
            "rule_name": rule_result["rule_name"],
            "recommendation_type": rule_result["recommendation_type"].value,
            "entity_type": rule_result["entity_type"].value,
            "priority": rule_result["priority"].value,
            "confidence": rule_result["confidence"].value,
        },
        "thresholds": {
            "target_acos": str(target_acos),
            "high_spend": str(max(default_budget * Decimal("2"), Decimal("20"))),
            "low_spend": "5",
            "negative_exact_min_clicks": 15,
            "negative_exact_min_spend": "10",
            "negative_exact_absolute_spend": "20",
            "negative_phrase_min_clicks": 15,
            "move_to_exact_min_orders": 2,
            "min_orders_for_bid_increase": 2,
            "max_bid_increase_multiplier": str(MAX_BID_INCREASE_MULTIPLIER),
            "max_bid_decrease_multiplier": str(MAX_BID_DECREASE_MULTIPLIER),
            "minimum_bid": str(MIN_BID),
        },
        "condition_signals": monitoring_metrics.condition_signals(snapshot, target_acos=target_acos, default_budget=default_budget, report_performance=rollups["report"]),
        "duplicate_overlap_signal": {
            "search_term_overlaps": snapshot.customer_search_term.strip().lower() in rollups["duplicates"]["overlapping_search_terms"],
            "target_overlaps": snapshot.targeting.strip().lower() in rollups["duplicates"]["overlapping_targets"],
        },
        "snapshot_metrics": metrics,
        "search_term_performance": rollups["search_term"][monitoring_metrics.search_term_key(snapshot)],
        "target_performance": rollups["target"][monitoring_metrics.target_key(snapshot)],
        "ad_group_performance": rollups["ad_group"][monitoring_metrics.ad_group_key(snapshot)],
        "campaign_performance": rollups["campaign"][snapshot.campaign_name],
        "report_performance": rollups["report"],
        "approval_boundary": {
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
            "amazon_ads_api_mutation": False,
        },
    }


def _build_performance_rollups(snapshots: list[MonitoringSnapshot]) -> dict:
    groups: dict[str, dict] = {
        "campaign": defaultdict(_empty_accumulator),
        "ad_group": defaultdict(_empty_accumulator),
        "target": defaultdict(_empty_accumulator),
        "search_term": defaultdict(_empty_accumulator),
    }
    report = _empty_accumulator()
    for snapshot in snapshots:
        for bucket, key in [
            ("campaign", snapshot.campaign_name),
            ("ad_group", _ad_group_key(snapshot)),
            ("target", _target_key(snapshot)),
            ("search_term", _search_term_key(snapshot)),
        ]:
            _add_snapshot(groups[bucket][key], snapshot)
        _add_snapshot(report, snapshot)
    return {
        "campaign": {key: _finalize_accumulator(value) for key, value in groups["campaign"].items()},
        "ad_group": {key: _finalize_accumulator(value) for key, value in groups["ad_group"].items()},
        "target": {key: _finalize_accumulator(value) for key, value in groups["target"].items()},
        "search_term": {key: _finalize_accumulator(value) for key, value in groups["search_term"].items()},
        "report": _finalize_accumulator(report),
    }


def _empty_accumulator() -> dict:
    return {"row_count": 0, "impressions": 0, "clicks": 0, "spend": Decimal("0"), "sales": Decimal("0"), "orders": 0, "units": 0}


def _add_snapshot(accumulator: dict, snapshot: MonitoringSnapshot) -> None:
    accumulator["row_count"] += 1
    accumulator["impressions"] += snapshot.impressions
    accumulator["clicks"] += snapshot.clicks
    accumulator["spend"] += snapshot.spend
    accumulator["sales"] += snapshot.sales
    accumulator["orders"] += snapshot.orders
    accumulator["units"] += snapshot.units or 0


def _finalize_accumulator(accumulator: dict) -> dict:
    clicks = Decimal(accumulator["clicks"])
    impressions = Decimal(accumulator["impressions"])
    spend = accumulator["spend"]
    sales = accumulator["sales"]
    orders = Decimal(accumulator["orders"])
    return {
        "row_count": accumulator["row_count"],
        "impressions": accumulator["impressions"],
        "clicks": accumulator["clicks"],
        "spend": str(spend.quantize(MONEY_QUANT)),
        "sales": str(sales.quantize(MONEY_QUANT)),
        "orders": accumulator["orders"],
        "units": accumulator["units"],
        "cpc": _decimal_str(_safe_divide(spend, clicks, MONEY_QUANT)),
        "ctr": _decimal_str(_safe_divide(clicks, impressions, RATE_QUANT)),
        "cvr": _decimal_str(_safe_divide(orders, clicks, RATE_QUANT)),
        "acos": _decimal_str(_safe_divide(spend, sales, RATE_QUANT)) if sales > 0 else None,
        "roas": _decimal_str(_safe_divide(sales, spend, RATE_QUANT)),
    }


def _data_quality_flags(snapshot: MonitoringSnapshot) -> list[str]:
    flags: list[str] = []
    if snapshot.clicks > snapshot.impressions:
        flags.append("clicks_exceed_impressions")
    if snapshot.orders > snapshot.clicks:
        flags.append("orders_exceed_clicks")
    if snapshot.spend > 0 and snapshot.clicks == 0:
        flags.append("spend_without_clicks")
    if snapshot.orders > 0 and snapshot.sales == 0:
        flags.append("orders_without_sales")
    data = _canonical_row_data(snapshot.raw_metrics_json or {})
    source_acos_key = "total advertising cost of sales acos"
    source_roas_key = "total return on advertising spend roas"
    source_acos = _safe_rate_value(data.get(source_acos_key))
    source_roas = _safe_rate_value(data.get(source_roas_key))
    if snapshot.sales > 0 and source_acos_key in data and _optional_text(data, source_acos_key) is None:
        flags.append("sales_with_blank_acos")
    if snapshot.sales > 0 and source_acos is not None:
        expected_acos = _safe_divide(snapshot.spend, snapshot.sales, RATE_QUANT)
        if expected_acos is not None and abs(source_acos - expected_acos) > RATE_TOLERANCE:
            flags.append("acos_mismatch")
    if snapshot.spend > 0 and source_roas is not None:
        expected_roas = _safe_divide(snapshot.sales, snapshot.spend, RATE_QUANT)
        if expected_roas is not None and abs(source_roas - expected_roas) > ROAS_TOLERANCE:
            flags.append("roas_mismatch")
    return flags


def _should_add_negative_phrase(*, snapshot: MonitoringSnapshot, default_budget: Decimal) -> bool:
    if snapshot.orders > 0 or snapshot.clicks < 15 or snapshot.spend < max(default_budget, Decimal("10")):
        return False
    return _match_type(snapshot) in {"broad", "phrase", "auto", "-"}


def _should_add_negative_exact(snapshot: MonitoringSnapshot) -> bool:
    if snapshot.orders > 0 or _is_asin(snapshot.customer_search_term):
        return False
    return (snapshot.clicks >= 15 and snapshot.spend >= Decimal("10")) or snapshot.spend >= Decimal("20")


def _should_decrease_bid(*, snapshot: MonitoringSnapshot, target_acos: Decimal) -> bool:
    return (
        _has_sales(snapshot)
        and snapshot.acos is not None
        and snapshot.acos > target_acos * Decimal("1.25")
        and (snapshot.clicks >= 8 or snapshot.spend >= Decimal("10"))
    )


def _should_increase_bid(*, snapshot: MonitoringSnapshot, target_acos: Decimal) -> bool:
    if not _has_sales(snapshot) or snapshot.orders < 2 or snapshot.acos is None:
        return False
    if snapshot.impressions >= 100:
        return False
    if snapshot.acos > target_acos * Decimal("0.90"):
        return False
    metrics = monitoring_metrics.snapshot_metrics(snapshot)
    cvr = Decimal(str(metrics.get("cvr") or "0"))
    if cvr < Decimal("0.0800") or snapshot.spend < Decimal("3"):
        return False
    return monitoring_metrics.condition_signals(snapshot, target_acos=target_acos, default_budget=Decimal("10"))["search_term_relevance"] != "low"


def _should_move_to_exact(*, snapshot: MonitoringSnapshot, target_acos: Decimal) -> bool:
    return (
        _has_sales(snapshot)
        and snapshot.orders >= 2
        and snapshot.acos is not None
        and snapshot.acos <= target_acos
        and _match_type(snapshot) in {"broad", "phrase", "auto", "-"}
        and not _is_asin(snapshot.customer_search_term)
    )


def _has_sales(snapshot: MonitoringSnapshot) -> bool:
    return snapshot.sales > 0 and snapshot.orders > 0


def _match_type(snapshot: MonitoringSnapshot) -> str:
    return (snapshot.match_type or "").strip().lower()


def _is_asin(value: str | None) -> bool:
    return bool(value and ASIN_PATTERN.fullmatch(value.strip()))


def _bounded_bid_multiplier(value: Decimal, *, minimum: Decimal, maximum: Decimal) -> Decimal:
    return min(max(value, minimum), maximum).quantize(RATE_QUANT)


def _recommended_bid(*, current_bid: Decimal | None, multiplier: Decimal | None) -> Decimal | None:
    if current_bid is None or multiplier is None:
        return None
    return max(MIN_BID, current_bid * multiplier).quantize(MONEY_QUANT)


def _search_term_key(snapshot: MonitoringSnapshot) -> str:
    return "|".join([snapshot.campaign_name, snapshot.ad_group_name, snapshot.targeting, snapshot.customer_search_term])


def _target_key(snapshot: MonitoringSnapshot) -> str:
    return "|".join([snapshot.campaign_name, snapshot.ad_group_name, snapshot.targeting])


def _ad_group_key(snapshot: MonitoringSnapshot) -> str:
    return "|".join([snapshot.campaign_name, snapshot.ad_group_name])


def _normalize_column(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()
    return normalized.replace("  ", " ")


def _canonical_row_data(row_data: dict) -> dict:
    data = {_normalize_column(key): value for key, value in row_data.items()}
    for canonical, variants in SP_SEARCH_TERM_COLUMN_ALIASES.items():
        if canonical in data:
            continue
        for variant in variants:
            if variant in data:
                data[canonical] = data[variant]
                break
    return data


def _product_detection_messages(rows: list[ParsedUploadRow]) -> list[dict]:
    groups: dict[str, dict] = {}
    for row in rows:
        data = _canonical_row_data(row.row_data_json)
        identifiers = _product_identifier_from_row(data)
        key = identifiers.get("asin") or identifiers.get("sku")
        if not key:
            continue
        group = groups.setdefault(
            key,
            {
                "key": key,
                "asin": identifiers.get("asin"),
                "sku": identifiers.get("sku"),
                "source": identifiers.get("source"),
                "rows": 0,
                "spend": Decimal("0"),
                "sales": Decimal("0"),
                "orders": 0,
            },
        )
        group["rows"] += 1
        try:
            group["spend"] += _money(data.get("spend"))
            group["sales"] += _money(data.get("7 day total sales"))
            group["orders"] += _int(data.get("7 day total orders"))
        except ValueError:
            continue
    if not groups:
        return []
    payload = [
        {
            "key": item["key"],
            "asin": item["asin"],
            "sku": item["sku"],
            "source": item["source"],
            "rows": item["rows"],
            "spend": str(item["spend"].quantize(MONEY_QUANT)),
            "sales": str(item["sales"].quantize(MONEY_QUANT)),
            "orders": item["orders"],
        }
        for item in sorted(groups.values(), key=lambda group: group["spend"], reverse=True)
    ]
    if len(payload) > 1:
        return [
            {
                "code": "MULTI_PRODUCT_REPORT_DETECTED",
                "severity": "warning",
                "message": "Multiple advertised product groups were detected. Review whether to import all rows under this product or split by advertised ASIN/SKU.",
                "details": {
                    "detected_product_groups": payload[:25],
                    "profile_creation_rule": "Use Advertised ASIN, Advertised SKU, or campaign-owned ASIN only. Never create product profiles from Customer Search Term ASINs.",
                },
            }
        ]
    return [
        {
            "code": "PRODUCT_GROUP_DETECTED",
            "severity": "info",
            "message": "One advertised product group was detected from product-owned report columns.",
            "details": {
                "detected_product_groups": payload,
                "profile_creation_rule": "Customer Search Term ASINs were not used for product detection.",
            },
        }
    ]


def _product_identifier_from_row(data: dict) -> dict[str, str | None]:
    for key in ("advertised asin", "campaign owned asin", "asin"):
        value = _optional_text(data, key)
        if value:
            return {"asin": value.upper(), "sku": _optional_text(data, "advertised sku") or _optional_text(data, "sku"), "source": key}
    for key in ("advertised sku", "sku"):
        value = _optional_text(data, key)
        if value:
            return {"asin": None, "sku": value, "source": key}
    return {"asin": None, "sku": None, "source": None}


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
    number = _decimal(value)
    if number < 0:
        raise ValueError(f"Metric value cannot be negative: {value}.")
    return int(number)


def _int_or_none(value) -> int | None:
    return None if value is None or value == "" else _int(value)


def _money(value) -> Decimal:
    return _decimal(value).quantize(MONEY_QUANT)


def _rate(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return _decimal(value, allow_percent=True).quantize(RATE_QUANT)


def _rate_or_money(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return _decimal(value, allow_percent=True).quantize(RATE_QUANT)


def _safe_rate_value(value) -> Decimal | None:
    try:
        return _rate_or_money(value)
    except ValueError:
        return None


def _decimal(value, *, allow_percent: bool = False) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    text = str(value).strip()
    is_percent = text.endswith("%")
    cleaned = text.replace("$", "").replace(",", "").replace("%", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value {value}.") from exc
    if number < 0:
        raise ValueError(f"Metric value cannot be negative: {value}.")
    return number / Decimal("100") if allow_percent and is_percent else number


def _safe_divide(numerator: Decimal, denominator: Decimal, quant: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator).quantize(quant)


def _decimal_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
