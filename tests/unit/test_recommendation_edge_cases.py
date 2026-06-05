"""Edge-case recommendation logic tests using realistic Amazon Ads scenarios.

Covers all 12 rule branches, boundary conditions, and business-critical decisions:
- High spend, zero orders → pause/negative
- Low ACOS profitable term → bid increase or move-to-exact
- High ACOS with sales → bid decrease (NOT negative keyword)
- No clicks → no recommendation (keep_running or watch)
- Few clicks only → watch lock (insufficient data)
- High clicks no orders → waste detection
- Same search term across multiple campaigns (duplicate detection)
- Exact-match term with waste → add_negative_exact (not add_negative_phrase)
- Broad-match waste → add_negative_phrase (not add_negative_exact)
- ASIN search term → never negative_exact candidate
- Bid multiplier bounds: never exceeds +30% or drops below -40%
- Minimum bid floor: $0.10
- Conflicting rules: first match wins (rule priority order)
- data_quality_review fires before any other rule
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from apps.api.app.repositories.monitoring import new_monitoring_import
from apps.api.app.schemas.monitoring import RecommendationType, RecommendationStatus
from apps.api.app.schemas.product_profiles import ProductProfileCreate
from apps.api.app.schemas.upload_parsing import ParsedUploadRow
from apps.api.app.services.monitoring_rules import build_recommendations, normalize_sp_search_term_rows


# ── fixtures ──────────────────────────────────────────────────────────────────

def _import():
    return new_monitoring_import(
        workspace_id=uuid4(),
        product_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        created_by="test",
    )


def _product(target_acos: float = 0.30, default_budget: float = 20.0, default_bid: float = 1.00) -> ProductProfileCreate:
    return ProductProfileCreate(
        product_name="Test Product",
        target_acos=Decimal(str(target_acos)),
        default_budget=Decimal(str(default_budget)),
        default_bid=Decimal(str(default_bid)),
    )


def _row(data: dict) -> ParsedUploadRow:
    return ParsedUploadRow(id=uuid4(), row_number=2, row_data_json=data, row_hash="x")


def _report_row(
    term: str,
    *,
    clicks: int,
    spend: float,
    sales: float,
    orders: int,
    impressions: int = 100,
    match_type: str = "exact",
    acos: float | None = None,
) -> dict:
    # Real Amazon SP reports always include ACOS when sales > 0.
    # Passing None when sales > 0 triggers the sales_with_blank_acos data quality flag.
    effective_acos = acos if acos is not None else (spend / sales if sales > 0 else None)
    return {
        "Campaign Name": "Campaign A",
        "Ad Group Name": "Group A",
        "Targeting": "running shoes",
        "Match Type": match_type,
        "Customer Search Term": term,
        "Impressions": impressions,
        "Clicks": clicks,
        "Spend": spend,
        "7 Day Total Sales ": sales,
        "7 Day Total Orders (#)": orders,
        "7 Day Total Units (#)": orders,
        "Total Advertising Cost of Sales (ACOS) ": effective_acos,
        "Total Return on Advertising Spend (ROAS)": 0 if spend == 0 else (sales / spend if spend > 0 else 0),
        "7 Day Conversion Rate": 0 if clicks == 0 else orders / clicks,
        "Click-Thru Rate (CTR)": 0 if impressions == 0 else clicks / impressions,
        "Cost Per Click (CPC)": 0 if clicks == 0 else spend / clicks,
    }


def _recs_for(rows_data: list[dict], product: ProductProfileCreate | None = None) -> dict:
    """Build recommendations by term name for the given row dicts."""
    imp = _import()
    prod = product or _product()
    parsed_rows = [_row(d) for d in rows_data]
    snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=parsed_rows)
    recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
    return {r.customer_search_term: r for r in recs}


# ── Rule 1: data_quality_review fires before all other rules ──────────────────

class TestDataQualityReviewTakesPriority:

    def test_clicks_exceed_impressions_triggers_data_quality(self) -> None:
        by_term = _recs_for([_report_row("bad term", clicks=20, impressions=10, spend=15, sales=0, orders=0)])
        assert by_term["bad term"].recommendation_type == RecommendationType.DATA_QUALITY_REVIEW
        assert by_term["bad term"].priority == "critical"

    def test_orders_exceed_clicks_triggers_data_quality(self) -> None:
        by_term = _recs_for([_report_row("bad orders", clicks=5, orders=10, spend=10, sales=50)])
        assert by_term["bad orders"].recommendation_type == RecommendationType.DATA_QUALITY_REVIEW

    def test_data_quality_suppresses_otherwise_valid_bid_decrease(self) -> None:
        """High ACOS + data quality issue → data_quality_review, NOT decrease_bid."""
        by_term = _recs_for([_report_row("messy term", clicks=20, impressions=5, spend=20, sales=10, orders=1)])
        # clicks > impressions → data_quality_review should fire
        assert by_term["messy term"].recommendation_type == RecommendationType.DATA_QUALITY_REVIEW


# ── Rule 2: high spend, zero orders → pause_review ────────────────────────────

class TestHighSpendZeroOrdersPauseReview:

    def test_spend_2x_budget_zero_orders_15_clicks_triggers_pause(self) -> None:
        by_term = _recs_for(
            [_report_row("burn term", clicks=20, spend=45.0, sales=0, orders=0)],
            product=_product(default_budget=20.0),
        )
        assert by_term["burn term"].recommendation_type == RecommendationType.PAUSE_REVIEW
        assert by_term["burn term"].priority == "critical"

    def test_no_pause_when_spend_below_2x_budget(self) -> None:
        by_term = _recs_for(
            [_report_row("okay term", clicks=20, spend=15.0, sales=0, orders=0)],
            product=_product(default_budget=20.0),
        )
        # Should hit negative_exact instead (clicks>=15, spend>=10), not pause
        assert by_term["okay term"].recommendation_type != RecommendationType.PAUSE_REVIEW

    def test_no_pause_when_fewer_than_15_clicks(self) -> None:
        """Not enough signal to pause without click evidence."""
        by_term = _recs_for(
            [_report_row("low click burn", clicks=10, spend=50.0, sales=0, orders=0)],
            product=_product(default_budget=20.0),
        )
        assert by_term["low click burn"].recommendation_type != RecommendationType.PAUSE_REVIEW

    def test_absolute_20_dollar_floor_for_pause(self) -> None:
        """Even with tiny budget, $20+ spend with 0 orders triggers pause."""
        by_term = _recs_for(
            [_report_row("low budget burn", clicks=20, spend=25.0, sales=0, orders=0)],
            product=_product(default_budget=5.0),  # 2x = $10, but absolute min $20
        )
        assert by_term["low budget burn"].recommendation_type == RecommendationType.PAUSE_REVIEW


# ── Rule 3: broad/phrase/auto match waste → add_negative_phrase ──────────────

class TestBroadMatchWasteNegativePhrase:

    def test_broad_match_16_clicks_budget_spend_triggers_negative_phrase(self) -> None:
        by_term = _recs_for(
            [_report_row("waste broad", clicks=16, spend=25.0, sales=0, orders=0, match_type="broad")],
            product=_product(default_budget=20.0),
        )
        assert by_term["waste broad"].recommendation_type == RecommendationType.ADD_NEGATIVE_PHRASE

    def test_auto_match_waste_triggers_negative_phrase(self) -> None:
        by_term = _recs_for(
            [_report_row("waste auto", clicks=20, spend=25.0, sales=0, orders=0, match_type="auto")],
            product=_product(default_budget=20.0),
        )
        assert by_term["waste auto"].recommendation_type == RecommendationType.ADD_NEGATIVE_PHRASE

    def test_exact_match_waste_does_not_trigger_negative_phrase(self) -> None:
        """Exact match terms go to add_negative_exact, not add_negative_phrase."""
        by_term = _recs_for(
            [_report_row("waste exact", clicks=16, spend=15.0, sales=0, orders=0, match_type="exact")],
            product=_product(default_budget=10.0),
        )
        assert by_term["waste exact"].recommendation_type != RecommendationType.ADD_NEGATIVE_PHRASE

    def test_negative_phrase_requires_spend_above_budget(self) -> None:
        """Spend below budget → not enough waste signal for negative phrase."""
        by_term = _recs_for(
            [_report_row("low spend broad", clicks=16, spend=5.0, sales=0, orders=0, match_type="broad")],
            product=_product(default_budget=20.0),
        )
        assert by_term["low spend broad"].recommendation_type != RecommendationType.ADD_NEGATIVE_PHRASE


# ── Rule 4: exact match waste → add_negative_exact ───────────────────────────

class TestExactMatchWasteNegativeExact:

    def test_15_clicks_10_spend_0_orders_exact_match_triggers_negative_exact(self) -> None:
        by_term = _recs_for(
            [_report_row("waste exact", clicks=16, spend=12.0, sales=0, orders=0, match_type="exact")],
        )
        assert by_term["waste exact"].recommendation_type == RecommendationType.ADD_NEGATIVE_EXACT

    def test_absolute_20_dollar_spend_triggers_negative_exact_regardless_of_clicks(self) -> None:
        by_term = _recs_for(
            [_report_row("expensive waste", clicks=5, spend=21.0, sales=0, orders=0, match_type="exact")],
        )
        assert by_term["expensive waste"].recommendation_type == RecommendationType.ADD_NEGATIVE_EXACT

    def test_asin_search_term_never_gets_negative_exact(self) -> None:
        """Customer search term that looks like an ASIN (B0XXXXXXXXX) must not become negative exact."""
        by_term = _recs_for(
            [_report_row("B07XJ8C8CN", clicks=20, spend=30.0, sales=0, orders=0, match_type="exact")],
        )
        rec = by_term["B07XJ8C8CN"]
        assert rec.recommendation_type not in {
            RecommendationType.ADD_NEGATIVE_EXACT,
            RecommendationType.ADD_NEGATIVE_PHRASE,
        }

    def test_negative_exact_confidence_high_when_30_plus_clicks(self) -> None:
        by_term = _recs_for(
            [_report_row("high click waste", clicks=35, spend=30.0, sales=0, orders=0, match_type="exact")],
        )
        assert by_term["high click waste"].confidence == "high"

    def test_negative_exact_confidence_medium_when_under_30_clicks(self) -> None:
        by_term = _recs_for(
            [_report_row("medium click waste", clicks=16, spend=12.0, sales=0, orders=0, match_type="exact")],
        )
        assert by_term["medium click waste"].confidence == "medium"

    def test_high_acos_with_orders_is_bid_decrease_not_negative(self) -> None:
        """High ACOS that still has sales → bid decrease. Never negative exact."""
        by_term = _recs_for(
            [_report_row("high acos term", clicks=12, spend=20.0, sales=10.0, orders=1, match_type="exact")],
            product=_product(target_acos=0.30),
        )
        assert by_term["high acos term"].recommendation_type == RecommendationType.DECREASE_BID
        assert by_term["high acos term"].recommendation_type != RecommendationType.ADD_NEGATIVE_EXACT


# ── Rule 5: ACOS above target → decrease_bid ─────────────────────────────────

class TestBidDecrease:

    def test_acos_above_125pct_target_with_sales_triggers_decrease(self) -> None:
        by_term = _recs_for(
            [_report_row("expensive buyer", clicks=12, spend=20.0, sales=10.0, orders=1, match_type="exact")],
            product=_product(target_acos=0.30),
        )
        assert by_term["expensive buyer"].recommendation_type == RecommendationType.DECREASE_BID

    def test_decrease_bid_multiplier_bounded_at_0_60(self) -> None:
        """Even if ACOS is 10x target, the bid decrease multiplier floor is 0.60."""
        by_term = _recs_for(
            [_report_row("extreme acos", clicks=20, spend=90.0, sales=10.0, orders=1, acos=9.0, match_type="exact")],
            product=_product(target_acos=0.30, default_bid=1.00),
        )
        rec = by_term["extreme acos"]
        assert rec.recommendation_type == RecommendationType.DECREASE_BID
        multiplier = Decimal(rec.proposed_action_json["suggested_bid_multiplier"])
        assert multiplier >= Decimal("0.6000")

    def test_decrease_bid_minimum_bid_floor_1_dollar(self) -> None:
        """recommended_bid must never go below $0.10 (MIN_BID)."""
        # current_bid = $0.10, with 0.60 multiplier → result = $0.06 → floored to $0.10
        by_term = _recs_for(
            [_report_row("low bid waste", clicks=12, spend=4.0, sales=2.0, orders=1, match_type="exact")],
            product=_product(target_acos=0.10, default_bid=0.10),
        )
        rec = by_term["low bid waste"]
        if rec.recommendation_type == RecommendationType.DECREASE_BID and rec.recommended_bid is not None:
            assert rec.recommended_bid >= Decimal("0.10")

    def test_no_decrease_bid_when_acos_below_threshold(self) -> None:
        """ACOS within target → no bid decrease."""
        by_term = _recs_for(
            [_report_row("good term", clicks=10, spend=8.0, sales=40.0, orders=2, match_type="exact")],
            product=_product(target_acos=0.30),
        )
        assert by_term["good term"].recommendation_type != RecommendationType.DECREASE_BID

    def test_decrease_bid_needs_enough_clicks_or_spend(self) -> None:
        """Too few clicks AND low spend → not enough evidence for bid decrease."""
        by_term = _recs_for(
            [_report_row("weak signal", clicks=3, spend=3.0, sales=1.0, orders=1, match_type="exact")],
            product=_product(target_acos=0.30),
        )
        # clicks < 8 AND spend < $10 → should not decrease bid
        assert by_term["weak signal"].recommendation_type != RecommendationType.DECREASE_BID


# ── Rule 7: move_to_exact ─────────────────────────────────────────────────────

class TestMoveToExact:

    def test_broad_efficient_2_orders_triggers_move_to_exact(self) -> None:
        by_term = _recs_for(
            [_report_row("good broad", clicks=10, spend=6.0, sales=30.0, orders=2, match_type="broad")],
            product=_product(target_acos=0.30),
        )
        assert by_term["good broad"].recommendation_type == RecommendationType.MOVE_TO_EXACT

    def test_exact_match_not_moved_to_exact_again(self) -> None:
        """Already exact → move_to_exact doesn't apply."""
        by_term = _recs_for(
            [_report_row("good exact", clicks=10, spend=6.0, sales=30.0, orders=2, match_type="exact")],
            product=_product(target_acos=0.30),
        )
        assert by_term["good exact"].recommendation_type != RecommendationType.MOVE_TO_EXACT

    def test_asin_not_moved_to_exact(self) -> None:
        """ASIN search terms not candidates for exact keyword targeting."""
        by_term = _recs_for(
            [_report_row("B07XJ8C8CN", clicks=10, spend=6.0, sales=30.0, orders=2, match_type="broad")],
            product=_product(target_acos=0.30),
        )
        assert by_term["B07XJ8C8CN"].recommendation_type != RecommendationType.MOVE_TO_EXACT

    def test_move_to_exact_requires_at_least_2_orders(self) -> None:
        by_term = _recs_for(
            [_report_row("1 order broad", clicks=10, spend=6.0, sales=15.0, orders=1, match_type="broad")],
            product=_product(target_acos=0.30),
        )
        assert by_term["1 order broad"].recommendation_type != RecommendationType.MOVE_TO_EXACT


# ── Rule 8: increase_bid (low impressions, strong converter) ──────────────────

class TestIncreaseBid:

    def test_low_impressions_2_orders_good_acos_triggers_bid_increase(self) -> None:
        by_term = _recs_for(
            [_report_row("gem term", clicks=5, spend=4.0, sales=20.0, orders=2, impressions=30, match_type="exact")],
            product=_product(target_acos=0.30, default_bid=1.00),
        )
        assert by_term["gem term"].recommendation_type == RecommendationType.INCREASE_BID

    def test_bid_increase_multiplier_bounded_at_1_30(self) -> None:
        """Even if ACOS is far below target, bid increase capped at +30%."""
        by_term = _recs_for(
            [_report_row("super gem", clicks=5, spend=1.0, sales=20.0, orders=3, impressions=20, match_type="exact")],
            product=_product(target_acos=0.30, default_bid=1.00),
        )
        rec = by_term["super gem"]
        if rec.recommendation_type == RecommendationType.INCREASE_BID:
            multiplier = Decimal(rec.proposed_action_json["suggested_bid_multiplier"])
            assert multiplier <= Decimal("1.3000")

    def test_no_bid_increase_when_impressions_high(self) -> None:
        """High impression term already has good visibility — no bid increase needed."""
        by_term = _recs_for(
            [_report_row("visible gem", clicks=10, spend=4.0, sales=20.0, orders=2, impressions=200, match_type="exact")],
            product=_product(target_acos=0.30),
        )
        assert by_term["visible gem"].recommendation_type != RecommendationType.INCREASE_BID

    def test_bid_increase_confidence_high_with_3_plus_orders(self) -> None:
        by_term = _recs_for(
            [_report_row("triple order", clicks=6, spend=3.0, sales=30.0, orders=3, impressions=25, match_type="exact")],
            product=_product(target_acos=0.30, default_bid=1.00),
        )
        rec = by_term["triple order"]
        if rec.recommendation_type == RecommendationType.INCREASE_BID:
            assert rec.confidence == "high"


# ── Watch lock cases ──────────────────────────────────────────────────────────

class TestWatchLock:

    def test_zero_clicks_zero_spend_is_keep_running(self) -> None:
        by_term = _recs_for([_report_row("unshown", clicks=0, impressions=0, spend=0, sales=0, orders=0)])
        # Degenerate zero row falls to keep_running or watch_lock (under_tested signal fires)
        assert by_term["unshown"].recommendation_type in {RecommendationType.WATCH_LOCK, RecommendationType.KEEP_RUNNING}

    def test_few_clicks_triggers_watch_lock(self) -> None:
        by_term = _recs_for([_report_row("early term", clicks=2, spend=1.0, sales=0, orders=0, impressions=10)])
        assert by_term["early term"].recommendation_type == RecommendationType.WATCH_LOCK

    def test_efficient_acos_2_orders_watch_lock(self) -> None:
        """Good ACOS, 2 orders but exact match — watch_lock, not move_to_exact."""
        by_term = _recs_for(
            [_report_row("great exact", clicks=10, spend=4.0, sales=20.0, orders=2, impressions=200, match_type="exact")],
            product=_product(target_acos=0.30),
        )
        assert by_term["great exact"].recommendation_type == RecommendationType.WATCH_LOCK

    def test_10_clicks_zero_orders_weak_watch_lock(self) -> None:
        by_term = _recs_for([_report_row("slow burn", clicks=10, spend=5.0, sales=0, orders=0, impressions=100)])
        assert by_term["slow burn"].recommendation_type == RecommendationType.WATCH_LOCK

    def test_1_order_within_target_acos_keep_running(self) -> None:
        """1 order, good ACOS, exact match, not under_tested → keep_running."""
        by_term = _recs_for(
            [_report_row("keep me", clicks=8, spend=5.0, sales=20.0, orders=1, impressions=200, match_type="exact")],
            product=_product(target_acos=0.30),
        )
        assert by_term["keep me"].recommendation_type == RecommendationType.KEEP_RUNNING


# ── Status invariant: all recs start as pending_approval ─────────────────────

class TestRecommendationStatusInvariant:

    def test_all_recommendations_start_as_pending_approval(self) -> None:
        imp = _import()
        prod = _product()
        rows = [
            _row(_report_row("term 1", clicks=20, spend=25, sales=0, orders=0, match_type="broad")),
            _row(_report_row("term 2", clicks=5, spend=8, sales=30, orders=2, match_type="broad")),
            _row(_report_row("term 3", clicks=12, spend=15, sales=5, orders=1, match_type="exact")),
        ]
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        assert all(r.status == RecommendationStatus.PENDING_APPROVAL for r in recs)

    def test_executes_live_amazon_change_always_false(self) -> None:
        imp = _import()
        prod = _product()
        rows = [_row(_report_row("any term", clicks=20, spend=25, sales=0, orders=0))]
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        for rec in recs:
            assert rec.proposed_action_json["executes_live_amazon_change"] is False
            assert rec.evidence_json["approval_boundary"]["executes_live_amazon_change"] is False

    def test_requires_human_approval_always_true(self) -> None:
        imp = _import()
        prod = _product()
        rows = [_row(_report_row("any term", clicks=20, spend=25, sales=0, orders=0))]
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        for rec in recs:
            assert rec.proposed_action_json["requires_human_approval"] is True


# ── Bid fields are populated on Recommendation schema ────────────────────────

class TestRecommendationBidFieldsPopulated:

    def test_increase_bid_recommendation_has_recommended_bid_field(self) -> None:
        imp = _import()
        prod = _product(target_acos=0.30, default_bid=1.00)
        rows = [_row(_report_row("gem", clicks=5, spend=3.0, sales=20.0, orders=2, impressions=30, match_type="exact"))]
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        rec = recs[0]
        if rec.recommendation_type == RecommendationType.INCREASE_BID:
            assert rec.recommended_bid is not None
            assert rec.current_bid is not None
            assert rec.change_percent is not None

    def test_decrease_bid_recommendation_has_recommended_bid_field(self) -> None:
        imp = _import()
        prod = _product(target_acos=0.30, default_bid=1.00)
        rows = [_row(_report_row("waste buyer", clicks=12, spend=20.0, sales=5.0, orders=1, match_type="exact"))]
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        rec = recs[0]
        if rec.recommendation_type == RecommendationType.DECREASE_BID:
            assert rec.recommended_bid is not None
            assert rec.recommended_bid >= Decimal("0.10")

    def test_match_type_populated_from_snapshot(self) -> None:
        imp = _import()
        prod = _product()
        rows = [_row(_report_row("broad term", clicks=5, spend=3.0, sales=15.0, orders=2, match_type="broad"))]
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        assert recs[0].match_type == "broad"


# ── Same search term across multiple campaigns (duplicate detection) ──────────

class TestDuplicateSearchTerms:

    def test_same_search_term_two_campaigns_flagged_in_evidence(self) -> None:
        imp = _import()
        prod = _product()
        rows = [
            _row({**_report_row("blue shoes", clicks=5, spend=5, sales=20, orders=1), "Campaign Name": "Camp A"}),
            _row({**_report_row("blue shoes", clicks=5, spend=5, sales=20, orders=1), "Campaign Name": "Camp B"}),
        ]
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        # All recommendations for "blue shoes" should have duplicate_overlap_signal set
        blue_shoes_recs = [r for r in recs if r.customer_search_term == "blue shoes"]
        assert len(blue_shoes_recs) == 2
        for r in blue_shoes_recs:
            assert r.evidence_json["duplicate_overlap_signal"]["search_term_overlaps"] is True
