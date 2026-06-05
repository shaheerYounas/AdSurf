"""Bulk Change Compiler Agent for AdSurf.

Generates Amazon-ready bulk sheet exports from approved recommendations.
This is the final output stage that turns recommendations into actionable
Amazon bulk upload files.

Supports:
- Amazon Sponsored Products bulk sheet format
- Campaign, Ad Group, Keyword, Product Target operations
- Bid changes, budget changes, negative keywords
- Before/after comparison
- Approval audit log
- Rollback reference
"""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from apps.api.app.schemas.monitoring import (
    Recommendation,
    RecommendationStatus,
    RecommendationType,
)

# Recommendation types that produce actionable bulk-sheet rows (not just informational).
_ACTIONABLE_TYPES = {
    RecommendationType.INCREASE_BID,
    RecommendationType.DECREASE_BID,
    RecommendationType.SET_BID,
    RecommendationType.PAUSE_KEYWORD,
    RecommendationType.PAUSE_TARGET,
    RecommendationType.PAUSE_REVIEW,
    RecommendationType.ADD_NEGATIVE_EXACT,
    RecommendationType.ADD_NEGATIVE_PHRASE,
    RecommendationType.HARVEST_TO_EXACT,
    RecommendationType.HARVEST_TO_PHRASE,
    RecommendationType.MOVE_TO_EXACT,
    RecommendationType.INCREASE_CAMPAIGN_BUDGET,
    RecommendationType.DECREASE_CAMPAIGN_BUDGET,
    RecommendationType.CREATE_EXACT_CAMPAIGN,
}


BULK_SHEET_HEADERS = [
    "Record ID",
    "Record Type",
    "Campaign ID",
    "Campaign",
    "Campaign Daily Budget",
    "Campaign Status",
    "Ad Group ID",
    "Ad Group",
    "Ad Group Status",
    "Keyword ID",
    "Keyword",
    "Keyword Type",
    "Keyword Bid",
    "Keyword Status",
    "Product Targeting ID",
    "Product Targeting Expression",
    "Product Targeting Bid",
    "Product Targeting Status",
    "Negative Keyword ID",
    "Negative Keyword",
    "Negative Keyword Type",
    "Negative Keyword Status",
    "Operation",
    "Notes",
]


def generate_bulk_sheet(
    approved_recommendations: list[Recommendation],
    *,
    workspace_id: UUID,
    export_name: str = "AdSurf Bulk Export",
) -> dict[str, Any]:
    """Generate an Amazon bulk sheet from approved recommendations.

    Returns a dict with:
    - csv_content: the CSV string
    - filename: suggested filename
    - summary: counts by operation type
    - audit_log: list of audit entries
    - before_after: before/after comparison data
    - rollback_reference: data needed to reverse changes
    """
    rows = []
    audit_log = []
    before_after = []
    rollback = []
    now = datetime.now(UTC)

    for rec in approved_recommendations:
        if rec.status != RecommendationStatus.APPROVED:
            continue

        bulk_rows = _recommendation_to_bulk_rows(rec, now)
        rows.extend(bulk_rows)

        audit_log.append({
            "recommendation_id": str(rec.id),
            "type": rec.recommendation_type.value,
            "campaign": rec.campaign_name,
            "ad_group": rec.ad_group_name,
            "targeting": rec.targeting,
            "keyword": rec.customer_search_term,
            "action": rec.proposed_action_json.get("action", ""),
            "before_value": _before_value(rec),
            "after_value": _after_value(rec),
            "change_pct": str(rec.change_percent) if rec.change_percent else None,
            "exported_at": now.isoformat(),
        })

        before_after.append({
            "entity": rec.customer_search_term or rec.targeting or rec.campaign_name,
            "type": rec.recommendation_type.value,
            "before": _before_value(rec),
            "after": _after_value(rec),
            "change": _change_description(rec),
        })

        rollback.append({
            "recommendation_id": str(rec.id),
            "entity_type": rec.entity_type.value,
            "entity_name": rec.campaign_name,
            "original_value": _before_value(rec),
            "rollback_action": _rollback_action(rec),
        })

    csv_content = _build_csv(rows)

    action_counts: dict[str, int] = {}
    for row in rows:
        op = row.get("Operation", "Unknown")
        action_counts[op] = action_counts.get(op, 0) + 1

    # Count by recommendation type for accurate summary (operation strings are Amazon bulk-sheet
    # format values like "Update"/"Create" and do not distinguish bid increase from decrease).
    type_counts: dict[str, int] = {}
    for rec in approved_recommendations:
        if rec.status == RecommendationStatus.APPROVED:
            type_counts[rec.recommendation_type.value] = type_counts.get(rec.recommendation_type.value, 0) + 1

    return {
        "csv_content": csv_content,
        "filename": f"{export_name.replace(' ', '_')}_{now.strftime('%Y%m%d_%H%M%S')}.csv",
        "generated_at": now.isoformat(),
        "total_rows": len(rows),
        "total_recommendations": sum(type_counts.values()),
        "summary": {
            "operations": action_counts,
            "bid_increases": type_counts.get(RecommendationType.INCREASE_BID.value, 0),
            "bid_decreases": type_counts.get(RecommendationType.DECREASE_BID.value, 0),
            "negative_keywords": type_counts.get(RecommendationType.ADD_NEGATIVE_EXACT.value, 0) + type_counts.get(RecommendationType.ADD_NEGATIVE_PHRASE.value, 0),
            "budget_changes": type_counts.get(RecommendationType.INCREASE_CAMPAIGN_BUDGET.value, 0) + type_counts.get(RecommendationType.DECREASE_CAMPAIGN_BUDGET.value, 0),
            "pauses": type_counts.get(RecommendationType.PAUSE_REVIEW.value, 0) + type_counts.get(RecommendationType.PAUSE_KEYWORD.value, 0) + type_counts.get(RecommendationType.PAUSE_TARGET.value, 0),
            "new_campaigns": type_counts.get(RecommendationType.CREATE_EXACT_CAMPAIGN.value, 0),
            "move_to_exact": type_counts.get(RecommendationType.MOVE_TO_EXACT.value, 0),
            "watch_insights": type_counts.get(RecommendationType.WATCH_LOCK.value, 0) + type_counts.get(RecommendationType.WATCH_ONLY.value, 0),
        },
        "audit_log": audit_log,
        "before_after": before_after,
        "rollback_reference": rollback,
        "safety_note": "This bulk sheet was generated by AdSurf. All changes were human-approved. No live Amazon Ads changes are executed automatically.",
    }


def _recommendation_to_bulk_rows(rec: Recommendation, now: datetime) -> list[dict[str, str]]:
    """Convert a recommendation into one or more bulk sheet rows."""
    rows = []
    base = {
        "Record ID": str(uuid4()),
        "Campaign": rec.campaign_name or "",
        "Ad Group": rec.ad_group_name or "",
        "Record Type": "",
        "Notes": f"AdSurf: {rec.explanation_json.get('summary', '')}",
    }

    rec_type = rec.recommendation_type
    action = rec.proposed_action_json.get("action", str(rec_type.value))

    if rec_type in {RecommendationType.INCREASE_BID, RecommendationType.DECREASE_BID, RecommendationType.SET_BID}:
        if rec.customer_search_term:
            # Keyword bid change
            rows.append({
                **base,
                "Record Type": "Keyword",
                "Keyword": rec.customer_search_term,
                "Keyword Type": rec.match_type or "Exact",
                "Keyword Bid": str(rec.recommended_bid or _decimal_from_action(rec, "recommended_bid") or ""),
                "Keyword Status": "Enabled",
                "Operation": "Update",
            })
        else:
            # Product targeting bid change
            rows.append({
                **base,
                "Record Type": "Product Targeting",
                "Product Targeting Expression": rec.targeting or "",
                "Product Targeting Bid": str(rec.recommended_bid or _decimal_from_action(rec, "recommended_bid") or ""),
                "Product Targeting Status": "Enabled",
                "Operation": "Update",
            })

    elif rec_type in {RecommendationType.PAUSE_KEYWORD, RecommendationType.PAUSE_TARGET, RecommendationType.PAUSE_REVIEW}:
        if rec.customer_search_term:
            rows.append({
                **base,
                "Record Type": "Keyword",
                "Keyword": rec.customer_search_term,
                "Keyword Status": "Paused",
                "Operation": "Update",
            })
        else:
            rows.append({
                **base,
                "Record Type": "Ad Group",
                "Ad Group Status": "Paused",
                "Operation": "Update",
            })

    elif rec_type in {RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE}:
        neg_type = "Negative Exact" if rec_type == RecommendationType.ADD_NEGATIVE_EXACT else "Negative Phrase"
        rows.append({
            **base,
            "Record Type": "Negative Keyword",
            "Negative Keyword": rec.customer_search_term or "",
            "Negative Keyword Type": neg_type,
            "Negative Keyword Status": "Enabled",
            "Operation": "Create",
        })

    elif rec_type in {RecommendationType.HARVEST_TO_EXACT, RecommendationType.HARVEST_TO_PHRASE, RecommendationType.MOVE_TO_EXACT}:
        # Create exact match keyword from converting search term
        match_type = "Exact" if rec_type in {RecommendationType.HARVEST_TO_EXACT, RecommendationType.MOVE_TO_EXACT} else "Phrase"
        rows.append({
            **base,
            "Record Type": "Keyword",
            "Keyword": rec.customer_search_term or "",
            "Keyword Type": match_type,
            "Keyword Bid": str(rec.recommended_bid or _decimal_from_action(rec, "recommended_bid") or ""),
            "Keyword Status": "Enabled",
            "Operation": "Create",
        })

    elif rec_type in {RecommendationType.INCREASE_CAMPAIGN_BUDGET, RecommendationType.DECREASE_CAMPAIGN_BUDGET}:
        rows.append({
            **base,
            "Record Type": "Campaign",
            "Campaign Daily Budget": str(rec.recommended_budget) if rec.recommended_budget else "",
            "Campaign Status": "Enabled",
            "Operation": "Update",
        })

    elif rec_type == RecommendationType.CREATE_EXACT_CAMPAIGN:
        rows.append({
            **base,
            "Record Type": "Campaign",
            "Campaign": f"{rec.campaign_name or 'New'} - Exact",
            "Campaign Daily Budget": str(rec.recommended_budget or "10"),
            "Campaign Status": "Enabled",
            "Operation": "Create",
        })

    elif rec_type in {RecommendationType.WATCH_LOCK, RecommendationType.WATCH_ONLY}:
        # WATCH types carry no bulk-sheet action — Amazon's importer rejects unknown Operation
        # values. These recommendations are informational only and must not appear in the CSV.
        pass

    return rows


def generate_approval_queue_summary(
    recommendations: list[Recommendation],
) -> dict[str, Any]:
    """Generate the approval queue dashboard summary.

    Returns counts, estimated savings, risk distribution, and bulk export readiness.
    """
    pending = [r for r in recommendations if r.status == RecommendationStatus.PENDING_APPROVAL]
    approved = [r for r in recommendations if r.status == RecommendationStatus.APPROVED]
    rejected = [r for r in recommendations if r.status == RecommendationStatus.REJECTED]

    bid_increases = [r for r in pending if r.recommendation_type == RecommendationType.INCREASE_BID]
    bid_decreases = [r for r in pending if r.recommendation_type == RecommendationType.DECREASE_BID]
    negatives = [r for r in pending if str(r.recommendation_type.value).startswith("add_negative")]
    budget_changes = [r for r in pending if r.recommendation_type in {
        RecommendationType.INCREASE_CAMPAIGN_BUDGET,
        RecommendationType.DECREASE_CAMPAIGN_BUDGET,
        RecommendationType.BUDGET_REVIEW,
    }]
    pauses = [r for r in pending if r.recommendation_type in {
        RecommendationType.PAUSE_KEYWORD,
        RecommendationType.PAUSE_TARGET,
        RecommendationType.PAUSE_REVIEW,
    }]

    wasted_spend = sum(
        float(r.input_metrics_json.get("spend", 0))
        for r in pending
        if int(r.input_metrics_json.get("orders", 0)) == 0
        and float(r.input_metrics_json.get("spend", 0)) > 0
    )

    total_spend = sum(float(r.input_metrics_json.get("spend", 0)) for r in recommendations)
    high_risk = len([r for r in pending if r.priority in {"critical", "high"}])

    return {
        "pending_approval": len(pending),
        "approved": len(approved),
        "rejected": len(rejected),
        "bid_increases": len(bid_increases),
        "bid_decreases": len(bid_decreases),
        "negative_keywords": len(negatives),
        "budget_changes": len(budget_changes),
        "pauses": len(pauses),
        "harvest_opportunities": len([r for r in pending if r.recommendation_type in {
            RecommendationType.HARVEST_TO_EXACT,
            RecommendationType.HARVEST_TO_PHRASE,
            RecommendationType.MOVE_TO_EXACT,
        }]),
        "total_spend_analyzed": total_spend,
        "wasted_spend_detected": wasted_spend,
        "estimated_monthly_savings": wasted_spend * 0.7,
        "high_risk_count": high_risk,
        "safe_for_bulk_export": high_risk == 0 and len(pending) == 0,
        "bulk_export_ready": len(pending) == 0 and len(approved) > 0,
    }


def _before_value(rec: Recommendation) -> str:
    """Get the 'before' value for audit comparison."""
    current_bid = rec.current_bid or _decimal_from_action(rec, "current_bid")
    if current_bid is not None:
        return f"${current_bid}"
    current_budget = rec.current_budget or _decimal_from_action(rec, "current_budget")
    if current_budget is not None:
        return f"${current_budget}"
    metrics = rec.input_metrics_json
    if "spend" in metrics:
        return f"Spend: ${metrics.get('spend', '0')}"
    return "N/A"


def _after_value(rec: Recommendation) -> str:
    """Get the 'after' value for audit comparison."""
    recommended_bid = rec.recommended_bid or _decimal_from_action(rec, "recommended_bid")
    if recommended_bid is not None:
        return f"${recommended_bid}"
    recommended_budget = rec.recommended_budget or _decimal_from_action(rec, "recommended_budget")
    if recommended_budget is not None:
        return f"${recommended_budget}"
    action = rec.proposed_action_json.get("action", "")
    return action.replace("_", " ").title()


def _decimal_from_action(rec: Recommendation, key: str) -> Decimal | None:
    """Safely read a Decimal value from proposed_action_json."""
    raw = rec.proposed_action_json.get(key)
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _change_description(rec: Recommendation) -> str:
    """Human-readable change description."""
    if rec.change_percent is not None:
        direction = "+" if rec.change_percent > 0 else ""
        return f"{direction}{rec.change_percent:.1f}%"
    return rec.recommendation_type.value.replace("_", " ").title()


def _rollback_action(rec: Recommendation) -> str:
    """Describe the rollback action needed."""
    if rec.recommendation_type in {RecommendationType.INCREASE_BID, RecommendationType.DECREASE_BID, RecommendationType.SET_BID}:
        return f"Restore bid to {_before_value(rec)}"
    if rec.recommendation_type in {RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE}:
        return "Remove negative keyword"
    if rec.recommendation_type in {RecommendationType.PAUSE_KEYWORD, RecommendationType.PAUSE_TARGET, RecommendationType.PAUSE_REVIEW}:
        return "Re-enable entity"
    if rec.recommendation_type in {RecommendationType.INCREASE_CAMPAIGN_BUDGET, RecommendationType.DECREASE_CAMPAIGN_BUDGET}:
        return f"Restore budget to {_before_value(rec)}"
    return "Manual rollback required"


def _build_csv(rows: list[dict[str, str]]) -> str:
    """Build CSV string from bulk sheet rows."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=BULK_SHEET_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def validate_export_readiness(
    recommendations: list[Recommendation],
    *,
    latest_import_id: UUID | None = None,
) -> dict[str, Any]:
    """Backend safety gate to run before generating a bulk export.

    Checks for:
    - Non-approved recommendations in the list
    - Stale recommendations (from an older import when a newer one exists)
    - Contradictory actions on the same entity (e.g. both increase_bid and decrease_bid)
    - Recommendations from insufficient data (WATCH_LOCK exported accidentally)
    - Missing search term on negative keyword recommendations

    Returns a dict with:
    - is_safe: bool
    - blocking_errors: list[str] — must be empty before exporting
    - warnings: list[str] — non-blocking issues to show the user
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Guard 1: all recs must be approved
    non_approved = [r for r in recommendations if r.status != RecommendationStatus.APPROVED]
    if non_approved:
        errors.append(
            f"{len(non_approved)} recommendation(s) are not in 'approved' status and must not be exported."
        )

    # Guard 2: stale recommendations from an older import
    if latest_import_id is not None:
        stale = [r for r in recommendations if r.monitoring_import_id != latest_import_id]
        if stale:
            warnings.append(
                f"{len(stale)} recommendation(s) were generated from an older import. "
                "A newer import exists. Review whether these decisions are still relevant."
            )

    # Guard 3: contradictory bid changes on the same entity
    _entity_actions: dict[str, list[str]] = {}
    for rec in recommendations:
        key = "|".join(filter(None, [rec.campaign_name, rec.ad_group_name, rec.customer_search_term or rec.targeting or ""]))
        _entity_actions.setdefault(key, []).append(rec.recommendation_type.value)

    for entity, actions in _entity_actions.items():
        has_increase = any("increase_bid" in a for a in actions)
        has_decrease = any("decrease_bid" in a for a in actions)
        has_pause = any("pause" in a for a in actions)
        has_negative = any("negative" in a for a in actions)
        if has_increase and has_decrease:
            errors.append(f"Contradictory bid change for '{entity}': both increase_bid and decrease_bid approved.")
        if has_pause and has_increase:
            warnings.append(f"'{entity}' has both pause and bid_increase approved — review before export.")
        if has_negative and has_increase:
            warnings.append(f"'{entity}' has both negative keyword and bid_increase — negative will supersede the bid change.")

    # Guard 4: non-actionable types sneaking into export list
    non_actionable = [r for r in recommendations if r.recommendation_type not in _ACTIONABLE_TYPES]
    if non_actionable:
        warnings.append(
            f"{len(non_actionable)} recommendation(s) have informational types "
            f"({', '.join(sorted({r.recommendation_type.value for r in non_actionable}))}) "
            "and will produce no rows in the bulk sheet."
        )

    # Guard 5: negative keyword recs must have a search term
    missing_term = [
        r for r in recommendations
        if r.recommendation_type in {RecommendationType.ADD_NEGATIVE_EXACT, RecommendationType.ADD_NEGATIVE_PHRASE}
        and not r.customer_search_term
    ]
    if missing_term:
        errors.append(
            f"{len(missing_term)} negative keyword recommendation(s) are missing the customer_search_term "
            "and cannot be written to the bulk sheet."
        )

    return {
        "is_safe": len(errors) == 0,
        "blocking_errors": errors,
        "warnings": warnings,
        "actionable_count": sum(1 for r in recommendations if r.recommendation_type in _ACTIONABLE_TYPES),
        "total_count": len(recommendations),
    }