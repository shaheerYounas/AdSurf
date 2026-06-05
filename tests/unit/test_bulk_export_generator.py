"""Unit tests for bulk_export_generator.py.

Tests cover:
- Each recommendation type maps to the correct CSV row structure
- WATCH_LOCK/WATCH_ONLY produce NO CSV rows (informational only)
- Summary counts are accurate (bid_increases, bid_decreases, negatives, etc.)
- total_recommendations counts only approved recs
- before_after and rollback_reference are populated
- _before_value/_after_value read from recommended_bid/current_bid (or proposed_action_json fallback)
- ADD_NEGATIVE_EXACT/PHRASE: correct Negative Keyword Type
- MOVE_TO_EXACT: creates Exact match keyword
- PAUSE_REVIEW with keyword: Paused status keyword row
- PAUSE_REVIEW without keyword: Paused ad group row
- Empty list → empty CSV (just header)
- Non-approved recs are skipped
"""

import csv
import io
from datetime import datetime, UTC
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.api.app.schemas.monitoring import (
    Recommendation,
    RecommendationConfidence,
    RecommendationEntityType,
    RecommendationPriority,
    RecommendationRiskLevel,
    RecommendationStatus,
    RecommendationType,
)
from apps.api.app.services.bulk_export_generator import (
    generate_approval_queue_summary,
    generate_bulk_sheet,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _rec(
    rec_type: RecommendationType,
    *,
    status: RecommendationStatus = RecommendationStatus.APPROVED,
    search_term: str | None = "blue running shoes",
    targeting: str | None = "running shoes",
    match_type: str | None = "Broad",
    campaign: str = "Camp A",
    ad_group: str = "Group A",
    recommended_bid: str | None = "1.2000",
    current_bid: str | None = "1.0000",
    change_percent: str | None = "20.00",
    priority: RecommendationPriority = RecommendationPriority.MEDIUM,
    input_metrics: dict | None = None,
) -> Recommendation:
    now = datetime.now(UTC)
    return Recommendation(
        id=uuid4(),
        workspace_id=uuid4(),
        product_id=uuid4(),
        recommendation_type=rec_type,
        status=status,
        priority=priority,
        rule_version_id="v1",
        rule_name="test_rule",
        entity_type=RecommendationEntityType.SEARCH_TERM,
        confidence=RecommendationConfidence.HIGH,
        campaign_name=campaign,
        ad_group_name=ad_group,
        targeting=targeting,
        customer_search_term=search_term,
        match_type=match_type,
        recommended_bid=Decimal(recommended_bid) if recommended_bid else None,
        current_bid=Decimal(current_bid) if current_bid else None,
        change_percent=Decimal(change_percent) if change_percent else None,
        input_metrics_json=input_metrics or {"spend": "10.00", "clicks": 10, "orders": 0, "sales": "0"},
        proposed_action_json={
            "action": rec_type.value,
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
            "recommended_bid": recommended_bid,
            "current_bid": current_bid,
            "change_percent": change_percent,
        },
        explanation_json={"summary": "Test recommendation"},
        created_at=now,
        updated_at=now,
    )


def _parse_csv(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


# ── test: each recommendation type ────────────────────────────────────────────

class TestRecommendationTypeToBulkRows:

    def test_increase_bid_produces_keyword_update_row(self) -> None:
        rec = _rec(RecommendationType.INCREASE_BID)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 1
        assert rows[0]["Record Type"] == "Keyword"
        assert rows[0]["Operation"] == "Update"
        assert rows[0]["Keyword"] == "blue running shoes"
        assert rows[0]["Keyword Bid"] == "1.2000"
        assert rows[0]["Keyword Status"] == "Enabled"

    def test_decrease_bid_produces_keyword_update_row(self) -> None:
        rec = _rec(RecommendationType.DECREASE_BID, recommended_bid="0.7000", change_percent="-30.00")
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 1
        assert rows[0]["Record Type"] == "Keyword"
        assert rows[0]["Operation"] == "Update"
        assert rows[0]["Keyword Bid"] == "0.7000"

    def test_increase_bid_no_keyword_produces_product_targeting_row(self) -> None:
        rec = _rec(RecommendationType.INCREASE_BID, search_term=None, targeting="asin=B0XXXXXXXXX")
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 1
        assert rows[0]["Record Type"] == "Product Targeting"
        assert rows[0]["Product Targeting Bid"] == "1.2000"

    def test_add_negative_exact_produces_negative_exact_row(self) -> None:
        rec = _rec(RecommendationType.ADD_NEGATIVE_EXACT, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 1
        assert rows[0]["Record Type"] == "Negative Keyword"
        assert rows[0]["Negative Keyword Type"] == "Negative Exact"
        assert rows[0]["Operation"] == "Create"
        assert rows[0]["Negative Keyword"] == "blue running shoes"

    def test_add_negative_phrase_produces_negative_phrase_row(self) -> None:
        rec = _rec(RecommendationType.ADD_NEGATIVE_PHRASE, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 1
        assert rows[0]["Negative Keyword Type"] == "Negative Phrase"

    def test_move_to_exact_creates_exact_keyword_row(self) -> None:
        rec = _rec(RecommendationType.MOVE_TO_EXACT, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 1
        assert rows[0]["Record Type"] == "Keyword"
        assert rows[0]["Keyword Type"] == "Exact"
        assert rows[0]["Operation"] == "Create"

    def test_pause_review_with_keyword_produces_paused_keyword_row(self) -> None:
        rec = _rec(RecommendationType.PAUSE_REVIEW, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 1
        assert rows[0]["Record Type"] == "Keyword"
        assert rows[0]["Keyword Status"] == "Paused"
        assert rows[0]["Operation"] == "Update"

    def test_pause_review_without_keyword_produces_paused_ad_group_row(self) -> None:
        rec = _rec(RecommendationType.PAUSE_REVIEW, search_term=None, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 1
        assert rows[0]["Record Type"] == "Ad Group"
        assert rows[0]["Ad Group Status"] == "Paused"

    def test_watch_lock_produces_no_csv_rows(self) -> None:
        """WATCH_LOCK is informational only — must not appear in Amazon bulk sheet."""
        rec = _rec(RecommendationType.WATCH_LOCK, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 0, "WATCH_LOCK should produce zero CSV rows"

    def test_watch_only_produces_no_csv_rows(self) -> None:
        rec = _rec(RecommendationType.WATCH_ONLY, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 0, "WATCH_ONLY should produce zero CSV rows"

    def test_keep_running_produces_no_csv_rows(self) -> None:
        """KEEP_RUNNING has no bulk action — should produce zero rows."""
        rec = _rec(RecommendationType.KEEP_RUNNING, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 0

    def test_harvest_to_exact_creates_exact_keyword(self) -> None:
        rec = _rec(RecommendationType.HARVEST_TO_EXACT, recommended_bid="0.8000")
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert rows[0]["Keyword Type"] == "Exact"
        assert rows[0]["Operation"] == "Create"

    def test_harvest_to_phrase_creates_phrase_keyword(self) -> None:
        rec = _rec(RecommendationType.HARVEST_TO_PHRASE, recommended_bid="0.8000")
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert rows[0]["Keyword Type"] == "Phrase"
        assert rows[0]["Operation"] == "Create"


# ── test: non-approved recs are skipped ───────────────────────────────────────

class TestNonApprovedSkipped:

    def test_pending_approval_recs_produce_no_rows(self) -> None:
        rec = _rec(RecommendationType.INCREASE_BID, status=RecommendationStatus.PENDING_APPROVAL)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        assert _parse_csv(result["csv_content"]) == []

    def test_rejected_recs_produce_no_rows(self) -> None:
        rec = _rec(RecommendationType.INCREASE_BID, status=RecommendationStatus.REJECTED)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        assert _parse_csv(result["csv_content"]) == []

    def test_mixed_approved_pending_only_approved_exported(self) -> None:
        approved = _rec(RecommendationType.INCREASE_BID)
        pending = _rec(RecommendationType.DECREASE_BID, status=RecommendationStatus.PENDING_APPROVAL)
        result = generate_bulk_sheet([approved, pending], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert len(rows) == 1  # only the approved one


# ── test: summary accuracy ───────────────────────────────────────────────────

class TestSummaryAccuracy:

    def test_bid_increase_count_in_summary(self) -> None:
        recs = [_rec(RecommendationType.INCREASE_BID) for _ in range(3)]
        result = generate_bulk_sheet(recs, workspace_id=uuid4())
        assert result["summary"]["bid_increases"] == 3

    def test_bid_decrease_count_in_summary(self) -> None:
        recs = [_rec(RecommendationType.DECREASE_BID, recommended_bid="0.7000") for _ in range(2)]
        result = generate_bulk_sheet(recs, workspace_id=uuid4())
        assert result["summary"]["bid_decreases"] == 2

    def test_negative_keyword_count_includes_both_types(self) -> None:
        recs = [
            _rec(RecommendationType.ADD_NEGATIVE_EXACT, recommended_bid=None, current_bid=None, change_percent=None),
            _rec(RecommendationType.ADD_NEGATIVE_PHRASE, recommended_bid=None, current_bid=None, change_percent=None),
        ]
        result = generate_bulk_sheet(recs, workspace_id=uuid4())
        assert result["summary"]["negative_keywords"] == 2

    def test_total_recommendations_counts_only_approved(self) -> None:
        approved = _rec(RecommendationType.INCREASE_BID)
        pending = _rec(RecommendationType.DECREASE_BID, status=RecommendationStatus.PENDING_APPROVAL)
        result = generate_bulk_sheet([approved, pending], workspace_id=uuid4())
        assert result["total_recommendations"] == 1

    def test_watch_lock_counted_in_watch_insights_not_csv_rows(self) -> None:
        rec = _rec(RecommendationType.WATCH_LOCK, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        assert result["summary"]["watch_insights"] == 1
        assert result["total_rows"] == 0

    def test_move_to_exact_counted_in_summary(self) -> None:
        rec = _rec(RecommendationType.MOVE_TO_EXACT, recommended_bid=None, current_bid=None, change_percent=None)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        assert result["summary"]["move_to_exact"] == 1


# ── test: empty export ────────────────────────────────────────────────────────

class TestEmptyExport:

    def test_empty_list_produces_header_only_csv(self) -> None:
        result = generate_bulk_sheet([], workspace_id=uuid4())
        rows = _parse_csv(result["csv_content"])
        assert rows == []
        assert "Record ID" in result["csv_content"]  # header present

    def test_empty_export_summary_all_zeros(self) -> None:
        result = generate_bulk_sheet([], workspace_id=uuid4())
        assert result["total_rows"] == 0
        assert result["total_recommendations"] == 0
        assert result["summary"]["bid_increases"] == 0


# ── test: safety metadata always present ─────────────────────────────────────

class TestSafetyMetadata:

    def test_safety_note_always_present(self) -> None:
        result = generate_bulk_sheet([], workspace_id=uuid4())
        assert "No live Amazon Ads changes are executed automatically" in result["safety_note"]

    def test_audit_log_entry_for_each_approved_rec(self) -> None:
        recs = [_rec(RecommendationType.INCREASE_BID), _rec(RecommendationType.DECREASE_BID, recommended_bid="0.7000")]
        result = generate_bulk_sheet(recs, workspace_id=uuid4())
        assert len(result["audit_log"]) == 2

    def test_rollback_reference_contains_restore_instructions(self) -> None:
        rec = _rec(RecommendationType.INCREASE_BID)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        assert len(result["rollback_reference"]) == 1
        assert "Restore bid" in result["rollback_reference"][0]["rollback_action"]

    def test_before_after_populated(self) -> None:
        rec = _rec(RecommendationType.INCREASE_BID)
        result = generate_bulk_sheet([rec], workspace_id=uuid4())
        ba = result["before_after"][0]
        assert ba["before"].startswith("$")
        assert ba["after"].startswith("$")


# ── test: generate_approval_queue_summary ────────────────────────────────────

class TestApprovalQueueSummary:

    def test_pending_count_correct(self) -> None:
        recs = [_rec(RecommendationType.INCREASE_BID, status=RecommendationStatus.PENDING_APPROVAL) for _ in range(5)]
        summary = generate_approval_queue_summary(recs)
        assert summary["pending_approval"] == 5

    def test_approved_and_rejected_counted_separately(self) -> None:
        recs = [
            _rec(RecommendationType.INCREASE_BID, status=RecommendationStatus.APPROVED),
            _rec(RecommendationType.DECREASE_BID, status=RecommendationStatus.REJECTED),
        ]
        summary = generate_approval_queue_summary(recs)
        assert summary["approved"] == 1
        assert summary["rejected"] == 1

    def test_wasted_spend_calculated_for_zero_order_recs(self) -> None:
        recs = [
            _rec(
                RecommendationType.ADD_NEGATIVE_EXACT,
                status=RecommendationStatus.PENDING_APPROVAL,
                input_metrics={"spend": "15.00", "orders": "0"},
                recommended_bid=None, current_bid=None, change_percent=None,
            ),
        ]
        summary = generate_approval_queue_summary(recs)
        assert summary["wasted_spend_detected"] == pytest.approx(15.0, abs=0.01)

    def test_high_risk_count_uses_priority_not_risk_level(self) -> None:
        """risk_level is often None; high_risk should use priority instead."""
        recs = [
            _rec(RecommendationType.PAUSE_REVIEW, status=RecommendationStatus.PENDING_APPROVAL, priority=RecommendationPriority.CRITICAL),
            _rec(RecommendationType.INCREASE_BID, status=RecommendationStatus.PENDING_APPROVAL, priority=RecommendationPriority.MEDIUM),
        ]
        summary = generate_approval_queue_summary(recs)
        assert summary["high_risk_count"] == 1

    def test_bulk_export_ready_when_all_reviewed(self) -> None:
        recs = [
            _rec(RecommendationType.INCREASE_BID, status=RecommendationStatus.APPROVED),
        ]
        summary = generate_approval_queue_summary(recs)
        assert summary["bulk_export_ready"] is True
        assert summary["safe_for_bulk_export"] is True
