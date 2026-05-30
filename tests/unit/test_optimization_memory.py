from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from apps.api.app.schemas.monitoring import (
    MonitoringSnapshot,
    Recommendation,
    RecommendationConfidence,
    RecommendationEntityType,
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)
from apps.api.app.services.optimization_memory import (
    archetype_for_snapshot,
    build_pattern_index,
    lookup_pattern_for_candidate,
)


def _snapshot(*, term: str, clicks: int, orders: int, spend: str, sales: str, acos: str | None = None, match_type: str = "exact") -> MonitoringSnapshot:
    return MonitoringSnapshot(
        id=uuid4(),
        workspace_id=uuid4(),
        product_id=uuid4(),
        monitoring_import_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        source_row_id=uuid4(),
        campaign_name="C",
        ad_group_name="G",
        targeting="t",
        match_type=match_type,
        customer_search_term=term,
        start_date="2026-05-01",
        end_date="2026-05-14",
        impressions=max(clicks * 10, 1),
        clicks=clicks,
        spend=Decimal(spend),
        sales=Decimal(sales),
        orders=orders,
        units=orders,
        cpc=Decimal("1.0000"),
        ctr=Decimal("0.1000"),
        cvr=Decimal("0.0500"),
        acos=Decimal(acos) if acos else None,
        roas=Decimal("0.0000"),
        raw_metrics_json={},
        created_at=datetime.now(UTC),
    )


def _approved_rec(snapshot: MonitoringSnapshot, rec_type: RecommendationType) -> Recommendation:
    now = datetime.now(UTC)
    return Recommendation(
        id=uuid4(),
        workspace_id=snapshot.workspace_id,
        product_id=snapshot.product_id,
        monitoring_import_id=snapshot.monitoring_import_id,
        snapshot_id=snapshot.id,
        recommendation_type=rec_type,
        entity_type=RecommendationEntityType.SEARCH_TERM,
        status=RecommendationStatus.APPROVED,
        priority=RecommendationPriority.HIGH,
        confidence=RecommendationConfidence.HIGH,
        rule_version_id="v1",
        rule_name="r",
        campaign_name=snapshot.campaign_name,
        ad_group_name=snapshot.ad_group_name,
        targeting=snapshot.targeting,
        customer_search_term=snapshot.customer_search_term,
        input_metrics_json={},
        proposed_action_json={"action": rec_type.value, "requires_human_approval": True, "executes_live_amazon_change": False},
        explanation_json={},
        created_at=now,
        updated_at=now,
    )


def test_archetype_groups_consistent_snapshots_into_same_bucket():
    s1 = _snapshot(term="term1", clicks=15, orders=0, spend="20.00", sales="0.00")
    s2 = _snapshot(term="term2", clicks=12, orders=0, spend="18.00", sales="0.00")
    a1 = archetype_for_snapshot(s1, target_acos=Decimal("0.30"))
    a2 = archetype_for_snapshot(s2, target_acos=Decimal("0.30"))
    assert a1 == a2
    assert a1["acos_band"] == "no_orders"
    assert a1["click_volume_band"] == "low"


def test_pending_recommendations_do_not_contribute_to_pattern_history():
    before = _snapshot(term="x", clicks=30, orders=0, spend="40.00", sales="0.00")
    after = _snapshot(term="x", clicks=4, orders=0, spend="5.00", sales="0.00")
    rec = _approved_rec(before, RecommendationType.ADD_NEGATIVE_EXACT)
    # Simulate "pending_approval" — should be skipped.
    rec = rec.model_copy(update={"status": RecommendationStatus.PENDING_APPROVAL})

    index = build_pattern_index(
        prior_recommendations=[rec],
        prior_snapshots=[before],
        follow_up_snapshots=[after],
        strategy_mode="balanced",
        target_acos=Decimal("0.30"),
    )
    assert index == {}


def test_successful_negative_pattern_is_aggregated_with_negative_acos_delta_or_spend_drop():
    before = _snapshot(term="x", clicks=30, orders=0, spend="40.00", sales="0.00")
    after = _snapshot(term="x", clicks=4, orders=0, spend="5.00", sales="0.00")
    rec = _approved_rec(before, RecommendationType.ADD_NEGATIVE_EXACT)

    index = build_pattern_index(
        prior_recommendations=[rec],
        prior_snapshots=[before],
        follow_up_snapshots=[after],
        strategy_mode="balanced",
        target_acos=Decimal("0.30"),
    )
    assert len(index) == 1
    outcome = next(iter(index.values()))
    assert outcome.sample_size == 1
    assert outcome.success_rate == 1.0


def test_lookup_returns_none_when_no_archetype_matches():
    before = _snapshot(term="x", clicks=30, orders=0, spend="40.00", sales="0.00")
    after = _snapshot(term="x", clicks=4, orders=0, spend="5.00", sales="0.00")
    index = build_pattern_index(
        prior_recommendations=[_approved_rec(before, RecommendationType.ADD_NEGATIVE_EXACT)],
        prior_snapshots=[before],
        follow_up_snapshots=[after],
        strategy_mode="balanced",
        target_acos=Decimal("0.30"),
    )

    # Look up a candidate from a totally different archetype.
    other = _snapshot(term="y", clicks=200, orders=10, spend="100.00", sales="500.00", acos="0.20", match_type="phrase")
    assert lookup_pattern_for_candidate(
        pattern_index=index,
        snapshot=other,
        action=RecommendationType.INCREASE_BID.value,
        strategy_mode="balanced",
        target_acos=Decimal("0.30"),
    ) is None


def test_lookup_returns_pattern_for_matching_archetype():
    before = _snapshot(term="x", clicks=30, orders=0, spend="40.00", sales="0.00")
    after = _snapshot(term="x", clicks=4, orders=0, spend="5.00", sales="0.00")
    index = build_pattern_index(
        prior_recommendations=[_approved_rec(before, RecommendationType.ADD_NEGATIVE_EXACT)],
        prior_snapshots=[before],
        follow_up_snapshots=[after],
        strategy_mode="balanced",
        target_acos=Decimal("0.30"),
    )

    # Same archetype (mid-clicks, no-orders, exact match) and same action.
    candidate = _snapshot(term="z", clicks=28, orders=0, spend="35.00", sales="0.00")
    found = lookup_pattern_for_candidate(
        pattern_index=index,
        snapshot=candidate,
        action=RecommendationType.ADD_NEGATIVE_EXACT.value,
        strategy_mode="balanced",
        target_acos=Decimal("0.30"),
    )
    assert found is not None
    assert found.sample_size == 1
