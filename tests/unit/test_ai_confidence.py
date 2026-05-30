from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from apps.api.app.schemas.monitoring import MonitoringSnapshot, RecommendationConfidence, RecommendationType
from apps.api.app.services.ai_confidence import compute_confidence


def _snapshot(*, clicks: int, orders: int, spend: str, sales: str, match_type: str = "exact", acos: str | None = None) -> MonitoringSnapshot:
    return MonitoringSnapshot(
        id=uuid4(),
        workspace_id=uuid4(),
        product_id=uuid4(),
        monitoring_import_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        source_row_id=uuid4(),
        campaign_name="Campaign A",
        ad_group_name="Group A",
        targeting="kw",
        match_type=match_type,
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


def test_high_clicks_high_spend_with_clear_waste_returns_high_confidence_for_negative():
    snap = _snapshot(clicks=60, orders=0, spend="80.00", sales="0.00")
    out = compute_confidence(
        snapshot=snap,
        recommendation_type=RecommendationType.ADD_NEGATIVE_EXACT,
        data_window_days=14,
    )
    assert out.confidence in {RecommendationConfidence.HIGH, RecommendationConfidence.VERY_HIGH}
    assert out.score >= 65


def test_negative_on_converting_term_returns_very_low_confidence():
    snap = _snapshot(clicks=60, orders=4, spend="80.00", sales="160.00")
    out = compute_confidence(
        snapshot=snap,
        recommendation_type=RecommendationType.ADD_NEGATIVE_EXACT,
        data_window_days=14,
    )
    assert out.confidence in {RecommendationConfidence.LOW, RecommendationConfidence.VERY_LOW, RecommendationConfidence.MEDIUM}
    assert any("converting orders" in n for n in out.notes)


def test_micro_data_returns_low_confidence():
    snap = _snapshot(clicks=2, orders=0, spend="1.50", sales="0.00")
    out = compute_confidence(
        snapshot=snap,
        recommendation_type=RecommendationType.DECREASE_BID,
        data_window_days=2,
    )
    assert out.confidence in {RecommendationConfidence.VERY_LOW, RecommendationConfidence.LOW}


def test_pattern_history_failure_pushes_confidence_down():
    snap = _snapshot(clicks=30, orders=0, spend="40.00", sales="0.00")
    bad_pattern = {"median_acos_delta_pct": 25.0, "sample_size": 10}
    out_with_bad = compute_confidence(
        snapshot=snap,
        recommendation_type=RecommendationType.ADD_NEGATIVE_EXACT,
        data_window_days=14,
        pattern_outcome=bad_pattern,
    )
    out_no_pattern = compute_confidence(
        snapshot=snap,
        recommendation_type=RecommendationType.ADD_NEGATIVE_EXACT,
        data_window_days=14,
    )
    assert out_with_bad.score < out_no_pattern.score


def test_pattern_history_success_lifts_confidence():
    snap = _snapshot(clicks=15, orders=0, spend="15.00", sales="0.00")
    good_pattern = {"median_acos_delta_pct": -25.0, "sample_size": 12}
    out_with_good = compute_confidence(
        snapshot=snap,
        recommendation_type=RecommendationType.ADD_NEGATIVE_EXACT,
        data_window_days=7,
        pattern_outcome=good_pattern,
    )
    out_no_pattern = compute_confidence(
        snapshot=snap,
        recommendation_type=RecommendationType.ADD_NEGATIVE_EXACT,
        data_window_days=7,
    )
    assert out_with_good.score > out_no_pattern.score
