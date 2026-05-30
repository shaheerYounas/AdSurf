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
from apps.api.app.services.ai_critic import critique


def _snapshot(*, clicks: int, orders: int, spend: str, sales: str = "0.00", acos: str | None = None) -> MonitoringSnapshot:
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
        match_type="exact",
        customer_search_term="term",
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


def _recommendation(snapshot: MonitoringSnapshot, *, rec_type: RecommendationType, priority: RecommendationPriority = RecommendationPriority.HIGH) -> Recommendation:
    now = datetime.now(UTC)
    return Recommendation(
        id=uuid4(),
        workspace_id=snapshot.workspace_id,
        product_id=snapshot.product_id,
        monitoring_import_id=snapshot.monitoring_import_id,
        snapshot_id=snapshot.id,
        recommendation_type=rec_type,
        entity_type=RecommendationEntityType.SEARCH_TERM,
        status=RecommendationStatus.PENDING_APPROVAL,
        priority=priority,
        confidence=RecommendationConfidence.HIGH,
        rule_version_id="v1",
        rule_name="test_rule",
        campaign_name=snapshot.campaign_name,
        ad_group_name=snapshot.ad_group_name,
        targeting=snapshot.targeting,
        customer_search_term=snapshot.customer_search_term,
        input_metrics_json={"clicks": snapshot.clicks, "orders": snapshot.orders, "spend": str(snapshot.spend)},
        proposed_action_json={"action": rec_type.value, "requires_human_approval": True, "executes_live_amazon_change": False},
        explanation_json={"summary": "test"},
        created_at=now,
        updated_at=now,
    )


def test_critic_blocks_negative_on_converting_term():
    snap = _snapshot(clicks=40, orders=3, spend="60.00", sales="120.00", acos="0.5")
    rec = _recommendation(snap, rec_type=RecommendationType.ADD_NEGATIVE_EXACT)

    result = critique(recommendations=[rec], snapshots=[snap])

    assert rec not in result.accepted
    assert any(str(rec.id) == f.recommendation_id and f.severity == "block" for f in result.findings)


def test_critic_blocks_negative_with_too_few_clicks():
    snap = _snapshot(clicks=5, orders=0, spend="30.00")
    rec = _recommendation(snap, rec_type=RecommendationType.ADD_NEGATIVE_EXACT)

    result = critique(recommendations=[rec], snapshots=[snap])

    assert rec not in result.accepted
    assert any("too little data" in f.reason for f in result.findings)


def test_critic_blocks_increase_bid_with_no_orders():
    snap = _snapshot(clicks=40, orders=0, spend="40.00")
    rec = _recommendation(snap, rec_type=RecommendationType.INCREASE_BID)

    result = critique(recommendations=[rec], snapshots=[snap])

    assert rec not in result.accepted
    assert any("zero orders" in f.reason for f in result.findings)


def test_critic_downgrades_negative_on_single_order_term():
    snap = _snapshot(clicks=30, orders=1, spend="40.00", sales="20.00", acos="2.0")
    rec = _recommendation(snap, rec_type=RecommendationType.ADD_NEGATIVE_EXACT)

    result = critique(recommendations=[rec], snapshots=[snap])

    assert rec.id in {r.id for r in result.accepted}
    accepted_rec = next(r for r in result.accepted if r.id == rec.id)
    assert accepted_rec.priority != RecommendationPriority.HIGH
    assert accepted_rec.explanation_json.get("critic_status") == "critic_downgraded"


def test_critic_passes_through_low_impact_items_without_review():
    snap = _snapshot(clicks=4, orders=0, spend="2.00")
    rec = _recommendation(snap, rec_type=RecommendationType.DECREASE_BID)

    result = critique(recommendations=[rec], snapshots=[snap])

    assert rec.id in {r.id for r in result.accepted}
    # Critic did not opine on this low-impact item.
    accepted_rec = next(r for r in result.accepted if r.id == rec.id)
    assert "critic_status" not in accepted_rec.explanation_json


def test_critic_clean_negative_passes():
    snap = _snapshot(clicks=30, orders=0, spend="35.00")
    rec = _recommendation(snap, rec_type=RecommendationType.ADD_NEGATIVE_EXACT)

    result = critique(recommendations=[rec], snapshots=[snap])

    assert rec.id in {r.id for r in result.accepted}
