"""Learning & Feedback Agent for AdSurf.

Compares previous recommendations with subsequent performance data
to create a learning loop. This turns the app from a static analyzer
into a real optimization system.

Capabilities:
- Compare previous recommendations with new report data
- Determine if implemented changes improved metrics
- Track ACOS improvement, spend reduction, ROAS changes
- Generate rule adjustment suggestions
- Build optimization memory over time
"""

from collections import defaultdict
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from apps.api.app.schemas.monitoring import (
    MonitoringSnapshot,
    Recommendation,
    RecommendationStatus,
    RecommendationType,
)


class FeedbackResult:
    def __init__(
        self,
        recommendation_id: UUID,
        implemented: bool,
        outcome: str,  # improved, worsened, unchanged, insufficient_data
        before_metrics: dict,
        after_metrics: dict,
        delta: dict,
        rule_adjustment_suggestion: str | None = None,
    ):
        self.recommendation_id = recommendation_id
        self.implemented = implemented
        self.outcome = outcome
        self.before_metrics = before_metrics
        self.after_metrics = after_metrics
        self.delta = delta
        self.rule_adjustment_suggestion = rule_adjustment_suggestion


def analyze_outcomes(
    previous_recommendations: list[Recommendation],
    current_snapshots: list[MonitoringSnapshot],
    *,
    target_acos: Decimal,
    minimum_confidence_threshold: str = "medium",
) -> dict[str, Any]:
    """Compare previous recommendations with current performance.

    Args:
        previous_recommendations: Recommendations from the last analysis cycle
        current_snapshots: Current monitoring snapshots
        target_acos: Target ACOS for the product
        minimum_confidence_threshold: Minimum confidence to consider for learning

    Returns:
        Dict with outcome analysis across all recommendations
    """
    # Build lookup from campaign+ad_group+targeting+search_term to snapshot
    snapshot_map: dict[str, MonitoringSnapshot] = {}
    for snapshot in current_snapshots:
        key = _snapshot_key(snapshot)
        snapshot_map[key] = snapshot

    results: list[dict] = []
    outcomes: dict[str, int] = defaultdict(int)
    rule_effectiveness: dict[str, dict] = defaultdict(lambda: {"correct": 0, "incorrect": 0, "total": 0})

    for rec in previous_recommendations:
        key = _recommendation_key(rec)
        current = snapshot_map.get(key)

        if current is None:
            outcomes["missing_from_report"] += 1
            continue

        # Determine if the recommendation was likely implemented
        implemented = _was_likely_implemented(rec, current)

        before_metrics = rec.input_metrics_json
        after_metrics = _snapshot_to_metrics(current)

        delta = _calculate_delta(before_metrics, after_metrics)
        outcome = _classify_outcome(rec, before_metrics, after_metrics, delta, target_acos)

        outcomes[outcome] += 1

        # Track rule effectiveness
        rule_name = rec.rule_name
        if outcome == "improved":
            rule_effectiveness[rule_name]["correct"] += 1
        elif outcome == "worsened":
            rule_effectiveness[rule_name]["incorrect"] += 1
        rule_effectiveness[rule_name]["total"] += 1

        results.append({
            "recommendation_id": str(rec.id),
            "recommendation_type": rec.recommendation_type.value,
            "campaign_name": rec.campaign_name,
            "ad_group_name": rec.ad_group_name,
            "targeting": rec.targeting,
            "customer_search_term": rec.customer_search_term,
            "was_implemented": implemented,
            "outcome": outcome,
            "before": before_metrics,
            "after": after_metrics,
            "delta": delta,
            "rule_name": rule_name,
            "rule_adjustment": _suggest_rule_adjustment(rec, outcome, before_metrics, after_metrics),
        })

    # Calculate rule effectiveness scores
    rule_scores = {}
    for rule, counts in rule_effectiveness.items():
        total = counts["total"]
        if total > 0:
            rule_scores[rule] = {
                "accuracy": counts["correct"] / total,
                "total_decisions": total,
                "correct": counts["correct"],
                "incorrect": counts["incorrect"],
            }

    return {
        "analysis_timestamp": datetime.now(UTC).isoformat(),
        "total_recommendations": len(previous_recommendations),
        "total_evaluated": len(results),
        "outcome_distribution": dict(outcomes),
        "improvement_rate": outcomes.get("improved", 0) / max(len(results), 1),
        "deterioration_rate": outcomes.get("worsened", 0) / max(len(results), 1),
        "results": results,
        "rule_effectiveness": rule_scores,
        "summary": _generate_learning_summary(results, outcomes, rule_scores),
        "next_cycle_suggestions": _generate_cycle_suggestions(results, rule_scores),
    }


def generate_optimization_memory(
    historical_cycles: list[dict[str, Any]],
    current_product_id: UUID,
) -> dict[str, Any]:
    """Build optimization memory from multiple analysis cycles.

    This creates a persistent learning record that grows over time.
    """
    if not historical_cycles:
        return {
            "product_id": str(current_product_id),
            "total_cycles": 0,
            "memory": {},
            "status": "no_data",
        }

    all_outcomes: list[str] = []
    rule_performance_over_time: dict[str, list[dict]] = defaultdict(list)
    improvement_trend: list[float] = []

    for cycle in historical_cycles:
        outcomes = cycle.get("outcome_distribution", {})
        all_outcomes.append(outcomes)
        improvement_trend.append(cycle.get("improvement_rate", 0))

        for rule, score in cycle.get("rule_effectiveness", {}).items():
            rule_performance_over_time[rule].append({
                "cycle": cycle.get("analysis_timestamp"),
                "accuracy": score.get("accuracy", 0),
            })

    # Trend analysis
    trend = "stable"
    if len(improvement_trend) >= 2:
        recent_trend = improvement_trend[-2:]
        if recent_trend[-1] > recent_trend[-2] * 1.1:
            trend = "improving"
        elif recent_trend[-1] < recent_trend[-2] * 0.9:
            trend = "declining"

    return {
        "product_id": str(current_product_id),
        "total_cycles": len(historical_cycles),
        "trend": trend,
        "improvement_rates": improvement_trend,
        "rule_performance_over_time": dict(rule_performance_over_time),
        "best_rules": sorted(
            [
                {"rule": rule, "avg_accuracy": sum(s["accuracy"] for s in scores) / len(scores)}
                for rule, scores in rule_performance_over_time.items()
            ],
            key=lambda x: x["avg_accuracy"],
            reverse=True,
        )[:5],
        "worst_rules": sorted(
            [
                {"rule": rule, "avg_accuracy": sum(s["accuracy"] for s in scores) / len(scores)}
                for rule, scores in rule_performance_over_time.items()
            ],
            key=lambda x: x["avg_accuracy"],
        )[:3],
    }


def _snapshot_key(snapshot: MonitoringSnapshot) -> str:
    return "|".join([
        snapshot.campaign_name.strip().lower(),
        snapshot.ad_group_name.strip().lower(),
        snapshot.targeting.strip().lower(),
        snapshot.customer_search_term.strip().lower(),
    ])


def _recommendation_key(rec: Recommendation) -> str:
    return "|".join([
        (rec.campaign_name or "").strip().lower(),
        (rec.ad_group_name or "").strip().lower(),
        (rec.targeting or "").strip().lower(),
        (rec.customer_search_term or "").strip().lower(),
    ])


def _snapshot_to_metrics(snapshot: MonitoringSnapshot) -> dict:
    return {
        "impressions": snapshot.impressions,
        "clicks": snapshot.clicks,
        "spend": str(snapshot.spend),
        "sales": str(snapshot.sales),
        "orders": snapshot.orders,
        "acos": str(snapshot.acos) if snapshot.acos else "0",
        "roas": str(snapshot.roas) if snapshot.roas else "0",
        "cpc": str(snapshot.cpc) if snapshot.cpc else "0",
        "ctr": str(snapshot.ctr) if snapshot.ctr else "0",
        "cvr": str(snapshot.cvr) if snapshot.cvr else "0",
    }


def _was_likely_implemented(rec: Recommendation, current: MonitoringSnapshot) -> bool:
    """Heuristic to determine if a recommendation was likely implemented.

    Checks for expected changes in the new data based on what was recommended.
    """
    rec_type = rec.recommendation_type

    if rec_type in {RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE}:
        # If negative was added, spend should be zero or impressions near zero
        return current.spend == 0 or current.impressions < 5

    if rec_type == RecommendationType.DECREASE_BID:
        # If bid was decreased, CPC should be lower
        old_cpc = float(rec.input_metrics_json.get("cpc", 0) or 0)
        new_cpc = float(current.cpc) if current.cpc else 0
        return new_cpc < old_cpc * 0.95 if old_cpc > 0 else False

    if rec_type == RecommendationType.INCREASE_BID:
        # If bid was increased, impressions or clicks should be higher
        old_clicks = int(rec.input_metrics_json.get("clicks", 0))
        return current.clicks > old_clicks * 1.1 if old_clicks > 0 else current.clicks > 0

    if rec_type in {RecommendationType.PAUSE_KEYWORD, RecommendationType.PAUSE_TARGET, RecommendationType.PAUSE_REVIEW}:
        # If paused, spend should be near zero
        return current.spend < Decimal("0.10")

    return False


def _calculate_delta(before: dict, after: dict) -> dict:
    """Calculate metric deltas between before and after states."""
    def _delta(b_key: str, a_key: str) -> float:
        b_val = float(before.get(b_key, 0) or 0)
        a_val = float(after.get(a_key, 0) or 0)
        if b_val == 0:
            return 100.0 if a_val > 0 else 0.0
        return ((a_val - b_val) / b_val) * 100

    return {
        "spend_change_pct": _delta("spend", "spend"),
        "sales_change_pct": _delta("sales", "sales"),
        "orders_change_pct": _delta("orders", "orders"),
        "acos_change_pct": _delta("acos", "acos"),
        "roas_change_pct": _delta("roas", "roas"),
        "cpc_change_pct": _delta("cpc", "cpc"),
        "clicks_change_pct": _delta("clicks", "clicks"),
    }


def _classify_outcome(
    rec: Recommendation,
    before: dict,
    after: dict,
    delta: dict,
    target_acos: Decimal,
) -> str:
    """Classify the outcome of a recommendation based on metric deltas."""
    before_acos = float(before.get("acos", 999) or 999)
    after_acos = float(after.get("acos", 999) or 999)
    before_sales = float(before.get("sales", 0) or 0)
    after_sales = float(after.get("sales", 0) or 0)
    before_spend = float(before.get("spend", 0) or 0)
    after_spend = float(after.get("spend", 0) or 0)

    rec_type = rec.recommendation_type

    # Check if there's insufficient data to evaluate
    before_clicks = int(before.get("clicks", 0))
    after_clicks = int(after.get("clicks", 0))
    if before_clicks < 5 or after_clicks < 5:
        return "insufficient_data"

    if rec_type == RecommendationType.DECREASE_BID:
        # Good: ACOS improved without losing all sales
        if after_acos < before_acos and after_sales > before_sales * 0.5:
            return "improved"
        if after_acos > before_acos * 1.10:
            return "worsened"

    elif rec_type == RecommendationType.INCREASE_BID:
        # Good: Sales increased without ACOS exploding
        if after_sales > before_sales and after_acos < before_acos * 1.20:
            return "improved"
        if after_spend > before_spend * 1.5 and after_sales < before_sales:
            return "worsened"

    elif rec_type in {RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE}:
        # Good: Spend eliminated without hurting other metrics
        if after_spend < before_spend * 0.20:
            return "improved"
        if after_spend > before_spend * 0.50:
            return "worsened"

    elif rec_type in {RecommendationType.PAUSE_KEYWORD, RecommendationType.PAUSE_TARGET, RecommendationType.PAUSE_REVIEW}:
        if after_spend < before_spend * 0.10:
            return "improved"
        if after_spend > before_spend * 0.30:
            return "worsened"

    elif rec_type in {RecommendationType.HARVEST_TO_EXACT, RecommendationType.MOVE_TO_EXACT}:
        if after_acos < before_acos * 0.90 and after_sales >= before_sales:
            return "improved"
        if after_acos > before_acos * 1.10:
            return "worsened"

    # Default: check general health
    if after_acos < before_acos and after_sales >= before_sales * 0.80:
        return "improved"
    if after_acos > before_acos * 1.20:
        return "worsened"

    return "unchanged"


def _suggest_rule_adjustment(
    rec: Recommendation,
    outcome: str,
    before: dict,
    after: dict,
) -> str | None:
    """Suggest rule adjustments based on outcomes."""
    if outcome == "improved":
        return None  # Rule is working, no adjustment needed
    if outcome == "worsened":
        return f"Rule '{rec.rule_name}' may need threshold review. Consider increasing evidence requirements or narrowing applicability."
    if outcome == "insufficient_data":
        return f"Rule '{rec.rule_name}' applied to entity with insufficient data. Increase minimum clicks/thresholds."
    return None


def _generate_learning_summary(
    results: list[dict],
    outcomes: dict[str, int],
    rule_scores: dict,
) -> str:
    """Generate a human-readable learning summary."""
    total = len(results)
    improved = outcomes.get("improved", 0)
    worsened = outcomes.get("worsened", 0)
    unchanged = outcomes.get("unchanged", 0)

    if total == 0:
        return "No data available for outcome learning yet."

    improvement_pct = (improved / total) * 100

    best_rules = sorted(rule_scores.items(), key=lambda x: x[1].get("accuracy", 0), reverse=True)[:3]
    best_rules_str = ", ".join([f"{r} ({s['accuracy']:.0%})" for r, s in best_rules]) if best_rules else "none"

    lines = [
        f"Out of {total} recommendations evaluated:",
        f"- {improved} improved ({improvement_pct:.0f}%)",
        f"- {worsened} worsened",
        f"- {unchanged} unchanged",
        f"Best performing rules: {best_rules_str}",
    ]
    return "\n".join(lines)


def _generate_cycle_suggestions(
    results: list[dict],
    rule_scores: dict,
) -> list[str]:
    """Generate suggestions for the next analysis cycle."""
    suggestions = []

    worsened_results = [r for r in results if r["outcome"] == "worsened"]
    if len(worsened_results) > len(results) * 0.3:
        suggestions.append("High proportion of worsened outcomes. Review strategy configuration and threshold settings.")

    insufficient = [r for r in results if r["outcome"] == "insufficient_data"]
    if len(insufficient) > len(results) * 0.2:
        suggestions.append("Many recommendations applied to entities with insufficient data. Increase minimum evidence thresholds.")

    low_accuracy_rules = [
        (rule, scores)
        for rule, scores in rule_scores.items()
        if scores.get("accuracy", 0) < 0.5 and scores.get("total", 0) >= 5
    ]
    for rule, scores in low_accuracy_rules[:3]:
        suggestions.append(f"Rule '{rule}' has {scores['accuracy']:.0%} accuracy over {scores['total']} decisions. Consider disabling or recalibrating.")

    if not suggestions:
        suggestions.append("System is performing well. Continue with current configuration.")

    return suggestions