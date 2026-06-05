"""Tests for validate_export_readiness — backend safety guard before bulk export."""

from datetime import datetime, UTC
from decimal import Decimal
from uuid import uuid4

from apps.api.app.schemas.monitoring import (
    Recommendation,
    RecommendationConfidence,
    RecommendationEntityType,
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)
from apps.api.app.services.bulk_export_generator import validate_export_readiness


def _rec(
    rec_type: RecommendationType,
    *,
    status: RecommendationStatus = RecommendationStatus.APPROVED,
    search_term: str | None = "test term",
    campaign: str = "Camp A",
    ad_group: str = "Group A",
    monitoring_import_id=None,
) -> Recommendation:
    now = datetime.now(UTC)
    import_id = monitoring_import_id or uuid4()
    return Recommendation(
        id=uuid4(),
        workspace_id=uuid4(),
        product_id=uuid4(),
        monitoring_import_id=import_id,
        recommendation_type=rec_type,
        status=status,
        priority=RecommendationPriority.MEDIUM,
        rule_version_id="v1",
        rule_name="rule",
        entity_type=RecommendationEntityType.SEARCH_TERM,
        confidence=RecommendationConfidence.HIGH,
        campaign_name=campaign,
        ad_group_name=ad_group,
        customer_search_term=search_term,
        input_metrics_json={},
        proposed_action_json={"action": rec_type.value, "requires_human_approval": True, "executes_live_amazon_change": False},
        explanation_json={"summary": "test"},
        created_at=now,
        updated_at=now,
    )


class TestValidateExportReadiness:

    def test_all_approved_returns_safe(self) -> None:
        recs = [_rec(RecommendationType.ADD_NEGATIVE_EXACT)]
        result = validate_export_readiness(recs)
        assert result["is_safe"] is True
        assert result["blocking_errors"] == []

    def test_pending_rec_blocks_export(self) -> None:
        recs = [_rec(RecommendationType.INCREASE_BID, status=RecommendationStatus.PENDING_APPROVAL)]
        result = validate_export_readiness(recs)
        assert result["is_safe"] is False
        assert len(result["blocking_errors"]) >= 1
        assert "1 recommendation(s) are not in 'approved' status" in result["blocking_errors"][0]

    def test_stale_recommendation_warns_but_does_not_block(self) -> None:
        latest = uuid4()
        old_import = uuid4()
        recs = [_rec(RecommendationType.INCREASE_BID, monitoring_import_id=old_import)]
        result = validate_export_readiness(recs, latest_import_id=latest)
        assert result["is_safe"] is True
        assert len(result["warnings"]) >= 1
        assert "older import" in result["warnings"][0]

    def test_same_import_no_stale_warning(self) -> None:
        latest = uuid4()
        recs = [_rec(RecommendationType.INCREASE_BID, monitoring_import_id=latest)]
        result = validate_export_readiness(recs, latest_import_id=latest)
        stale_warnings = [w for w in result["warnings"] if "older import" in w]
        assert stale_warnings == []

    def test_contradictory_increase_and_decrease_on_same_entity_blocks(self) -> None:
        recs = [
            _rec(RecommendationType.INCREASE_BID, search_term="running shoes", campaign="C", ad_group="G"),
            _rec(RecommendationType.DECREASE_BID, search_term="running shoes", campaign="C", ad_group="G"),
        ]
        result = validate_export_readiness(recs)
        assert result["is_safe"] is False
        contradiction_errors = [e for e in result["blocking_errors"] if "Contradictory bid change" in e]
        assert len(contradiction_errors) == 1

    def test_negative_keyword_without_search_term_blocks_export(self) -> None:
        recs = [_rec(RecommendationType.ADD_NEGATIVE_EXACT, search_term=None)]
        result = validate_export_readiness(recs)
        assert result["is_safe"] is False
        assert any("missing the customer_search_term" in e for e in result["blocking_errors"])

    def test_watch_lock_warns_about_non_actionable_type(self) -> None:
        recs = [_rec(RecommendationType.WATCH_LOCK)]
        result = validate_export_readiness(recs)
        assert result["is_safe"] is True  # not a blocking error, just a warning
        assert any("informational types" in w for w in result["warnings"])

    def test_actionable_count_correct(self) -> None:
        recs = [
            _rec(RecommendationType.INCREASE_BID),
            _rec(RecommendationType.WATCH_LOCK),
            _rec(RecommendationType.KEEP_RUNNING),
        ]
        result = validate_export_readiness(recs)
        assert result["actionable_count"] == 1
        assert result["total_count"] == 3

    def test_pause_and_bid_increase_on_same_entity_warns(self) -> None:
        recs = [
            _rec(RecommendationType.INCREASE_BID, search_term="shoes", campaign="C", ad_group="G"),
            _rec(RecommendationType.PAUSE_REVIEW, search_term="shoes", campaign="C", ad_group="G"),
        ]
        result = validate_export_readiness(recs)
        assert any("pause" in w for w in result["warnings"])

    def test_empty_recommendations_is_safe(self) -> None:
        result = validate_export_readiness([])
        assert result["is_safe"] is True
        assert result["total_count"] == 0
        assert result["actionable_count"] == 0
