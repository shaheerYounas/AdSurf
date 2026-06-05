"""Unit tests for monitoring_metrics.py — all calculation formulas.

Tests cover:
- CPC, CTR, CVR, ACOS, ROAS, CPA correctness
- Division-by-zero safety (_safe_divide returns None, not crash)
- Zero-impressions, zero-clicks, zero-spend, zero-sales edge cases
- share metrics: click_share, spend_share, sales_share
- condition_signals: every signal flag
- build_performance_rollups: aggregation across multiple snapshots
- duplicate detection in rollups
"""

from datetime import datetime, UTC
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.api.app.schemas.monitoring import MonitoringSnapshot
from apps.api.app.services import monitoring_metrics


# ── helpers ──────────────────────────────────────────────────────────────────

def _snap(
    *,
    campaign: str = "Camp A",
    ad_group: str = "Group A",
    targeting: str = "keyword",
    match_type: str | None = "exact",
    search_term: str = "test term",
    impressions: int = 100,
    clicks: int = 10,
    spend: str = "10.00",
    sales: str = "40.00",
    orders: int = 2,
    units: int | None = 2,
    cpc: str | None = None,
    ctr: str | None = None,
    cvr: str | None = None,
    acos: str | None = None,
    roas: str | None = None,
) -> MonitoringSnapshot:
    now = datetime.now(UTC)
    return MonitoringSnapshot(
        id=uuid4(),
        workspace_id=uuid4(),
        product_id=uuid4(),
        monitoring_import_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        source_row_id=uuid4(),
        campaign_name=campaign,
        ad_group_name=ad_group,
        targeting=targeting,
        match_type=match_type,
        customer_search_term=search_term,
        impressions=impressions,
        clicks=clicks,
        spend=Decimal(spend),
        sales=Decimal(sales),
        orders=orders,
        units=units,
        cpc=Decimal(cpc) if cpc else None,
        ctr=Decimal(ctr) if ctr else None,
        cvr=Decimal(cvr) if cvr else None,
        acos=Decimal(acos) if acos else None,
        roas=Decimal(roas) if roas else None,
        created_at=now,
    )


# ── snapshot_metrics: derived calculations ────────────────────────────────────

class TestSnapshotMetricsCalculations:

    def test_cpc_calculated_from_spend_and_clicks(self) -> None:
        snap = _snap(spend="15.00", clicks=5, cpc=None)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["cpc"] == "3.0000"

    def test_ctr_calculated_from_clicks_and_impressions(self) -> None:
        snap = _snap(clicks=5, impressions=100, ctr=None)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["ctr"] == "0.0500"

    def test_cvr_calculated_from_orders_and_clicks(self) -> None:
        snap = _snap(clicks=10, orders=2, cvr=None)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["cvr"] == "0.2000"

    def test_acos_calculated_from_spend_and_sales(self) -> None:
        snap = _snap(spend="10.00", sales="40.00", acos=None)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["acos"] == "0.2500"

    def test_roas_calculated_from_sales_and_spend(self) -> None:
        snap = _snap(spend="10.00", sales="40.00", roas=None)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["roas"] == "4.0000"

    def test_cpa_equals_spend_divided_by_orders(self) -> None:
        snap = _snap(spend="20.00", orders=4)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["cpa"] == "5.0000"

    def test_source_cpc_used_when_provided(self) -> None:
        snap = _snap(spend="15.00", clicks=5, cpc="2.5000")
        m = monitoring_metrics.snapshot_metrics(snap)
        # pre-populated value wins
        assert m["cpc"] == "2.5000"

    def test_source_acos_used_when_provided(self) -> None:
        snap = _snap(spend="10.00", sales="40.00", acos="0.2700")
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["acos"] == "0.2700"

    def test_acos_none_when_sales_zero(self) -> None:
        snap = _snap(sales="0.00", orders=0, acos=None)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["acos"] is None

    def test_roas_none_when_spend_zero(self) -> None:
        snap = _snap(spend="0.00", sales="0.00")
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["roas"] is None

    def test_cpc_none_when_clicks_zero(self) -> None:
        snap = _snap(clicks=0, spend="0.00")
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["cpc"] is None

    def test_ctr_none_when_impressions_zero(self) -> None:
        snap = _snap(impressions=0, clicks=0)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["ctr"] is None

    def test_cvr_none_when_clicks_zero(self) -> None:
        snap = _snap(clicks=0, orders=0)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["cvr"] is None

    def test_cpa_none_when_orders_zero(self) -> None:
        snap = _snap(orders=0)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["cpa"] is None

    def test_zero_order_spend_reflects_spend_when_no_orders(self) -> None:
        snap = _snap(spend="12.50", orders=0, sales="0.00")
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["zero_order_spend"] == "12.50"
        assert m["wasted_spend"] == "12.50"

    def test_zero_order_spend_is_zero_when_orders_exist(self) -> None:
        snap = _snap(spend="12.50", orders=1, sales="40.00")
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["zero_order_spend"] == "0"
        assert m["wasted_spend"] == "0"

    def test_share_metrics_calculated_correctly(self) -> None:
        snap = _snap(clicks=10, spend="20.00", sales="80.00")
        report = {"clicks": 100, "spend": "200.0000", "sales": "800.0000"}
        m = monitoring_metrics.snapshot_metrics(snap, report_performance=report)
        assert m["click_share"] == "0.1000"
        assert m["spend_share"] == "0.1000"
        assert m["sales_share"] == "0.1000"

    def test_share_metrics_none_when_report_none(self) -> None:
        snap = _snap(clicks=10, spend="20.00", sales="80.00")
        m = monitoring_metrics.snapshot_metrics(snap, report_performance=None)
        assert m["click_share"] is None
        assert m["spend_share"] is None
        assert m["sales_share"] is None

    def test_all_zero_row_does_not_crash(self) -> None:
        snap = _snap(impressions=0, clicks=0, spend="0.00", sales="0.00", orders=0)
        m = monitoring_metrics.snapshot_metrics(snap)
        assert m["cpc"] is None
        assert m["ctr"] is None
        assert m["cvr"] is None
        assert m["acos"] is None
        assert m["roas"] is None
        assert m["cpa"] is None


# ── condition_signals ─────────────────────────────────────────────────────────

class TestConditionSignals:
    TARGET_ACOS = Decimal("0.30")
    BUDGET = Decimal("20.00")

    def test_high_click_zero_order_signal(self) -> None:
        snap = _snap(clicks=15, orders=0, sales="0.00")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["high_click_zero_order"] is True

    def test_high_click_zero_order_false_below_threshold(self) -> None:
        snap = _snap(clicks=9, orders=0, sales="0.00")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["high_click_zero_order"] is False

    def test_under_tested_when_few_clicks(self) -> None:
        snap = _snap(clicks=2, impressions=50)
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["under_tested"] is True

    def test_under_tested_when_few_impressions(self) -> None:
        snap = _snap(clicks=5, impressions=5)
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["under_tested"] is True

    def test_not_under_tested_with_adequate_data(self) -> None:
        snap = _snap(clicks=5, impressions=50)
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["under_tested"] is False

    def test_strong_converter_signal(self) -> None:
        snap = _snap(spend="6.00", sales="30.00", orders=3, acos="0.2000")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["strong_converter"] is True

    def test_strong_converter_false_high_acos(self) -> None:
        snap = _snap(spend="20.00", sales="30.00", orders=3, acos="0.6667")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["strong_converter"] is False

    def test_high_acos_signal(self) -> None:
        snap = _snap(spend="15.00", sales="20.00", orders=1, acos="0.7500")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["high_acos"] is True

    def test_budget_pressure_signal(self) -> None:
        snap = _snap(spend="17.00", sales="50.00", orders=3, roas="2.9412")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["budget_pressure"] is True

    def test_budget_pressure_false_low_roas(self) -> None:
        snap = _snap(spend="17.00", sales="10.00", orders=1, roas="0.5882")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["budget_pressure"] is False

    def test_broad_match_waste_signal(self) -> None:
        snap = _snap(match_type="broad", clicks=12, orders=0, sales="0.00")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["broad_match_waste"] is True

    def test_over_tested_signal(self) -> None:
        snap = _snap(clicks=25, orders=0, sales="0.00")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["over_tested"] is True

    def test_match_type_risk_high_for_broad(self) -> None:
        snap = _snap(match_type="broad")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["match_type_risk"] == "high"

    def test_match_type_risk_medium_for_phrase(self) -> None:
        snap = _snap(match_type="phrase")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["match_type_risk"] == "medium"

    def test_match_type_risk_low_for_exact(self) -> None:
        snap = _snap(match_type="exact")
        s = monitoring_metrics.condition_signals(snap, target_acos=self.TARGET_ACOS, default_budget=self.BUDGET)
        assert s["match_type_risk"] == "low"


# ── build_performance_rollups ─────────────────────────────────────────────────

class TestBuildPerformanceRollups:

    def test_report_level_aggregates_all_snapshots(self) -> None:
        s1 = _snap(campaign="C1", clicks=10, spend="5.00", sales="20.00", orders=1)
        s2 = _snap(campaign="C2", clicks=20, spend="10.00", sales="40.00", orders=2)
        rollups = monitoring_metrics.build_performance_rollups([s1, s2])
        report = rollups["report"]
        assert report["clicks"] == 30
        assert Decimal(report["spend"]) == Decimal("15.0000")
        assert Decimal(report["sales"]) == Decimal("60.0000")
        assert report["orders"] == 3

    def test_campaign_rollup_groups_by_campaign_name(self) -> None:
        s1 = _snap(campaign="Camp X", search_term="term 1", clicks=5, spend="5.00", sales="10.00", orders=1)
        s2 = _snap(campaign="Camp X", search_term="term 2", clicks=5, spend="5.00", sales="10.00", orders=1)
        s3 = _snap(campaign="Camp Y", search_term="term 3", clicks=10, spend="10.00", sales="20.00", orders=2)
        rollups = monitoring_metrics.build_performance_rollups([s1, s2, s3])
        assert rollups["campaign"]["Camp X"]["clicks"] == 10
        assert rollups["campaign"]["Camp Y"]["clicks"] == 10

    def test_duplicate_search_term_detection(self) -> None:
        """Same search term appearing in two different campaigns → duplicate flag."""
        s1 = _snap(campaign="Camp A", search_term="blue shoes", targeting="keyword_a")
        s2 = _snap(campaign="Camp B", search_term="blue shoes", targeting="keyword_b")
        rollups = monitoring_metrics.build_performance_rollups([s1, s2])
        assert "blue shoes" in rollups["duplicates"]["overlapping_search_terms"]

    def test_no_duplicate_when_term_appears_once(self) -> None:
        snap = _snap(search_term="unique term")
        rollups = monitoring_metrics.build_performance_rollups([snap])
        assert "unique term" not in rollups["duplicates"]["overlapping_search_terms"]

    def test_rollup_acos_none_when_no_sales_in_group(self) -> None:
        snap = _snap(sales="0.00", orders=0)
        rollups = monitoring_metrics.build_performance_rollups([snap])
        assert rollups["report"]["acos"] is None

    def test_rollup_includes_share_metrics(self) -> None:
        s1 = _snap(campaign="Camp A", clicks=50, spend="50.00", sales="200.00", orders=5)
        s2 = _snap(campaign="Camp B", clicks=50, spend="50.00", sales="200.00", orders=5)
        rollups = monitoring_metrics.build_performance_rollups([s1, s2])
        camp_a = rollups["campaign"]["Camp A"]
        assert camp_a["click_share"] == "0.5000"
        assert camp_a["spend_share"] == "0.5000"
        assert camp_a["sales_share"] == "0.5000"

    def test_empty_snapshots_returns_empty_rollups(self) -> None:
        rollups = monitoring_metrics.build_performance_rollups([])
        assert rollups["report"]["clicks"] == 0
        assert rollups["report"]["orders"] == 0
        assert rollups["campaign"] == {}
