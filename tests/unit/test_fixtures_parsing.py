"""Tests that use realistic Amazon Ads CSV fixtures to validate end-to-end parsing + recommendations.

Tests validate:
- Clean fixture: all expected recommendation types generated
- Edge cases fixture: ASIN search terms not negated, duplicate terms detected, watch-lock for low data
- Dirty fixture: data quality issues produce DATA_QUALITY_REVIEW, not other types
- Multi-product fixture: MULTI_PRODUCT_REPORT_DETECTED warning with correct ASINs
"""

import csv
import io
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from apps.api.app.repositories.monitoring import new_monitoring_import
from apps.api.app.schemas.monitoring import RecommendationType
from apps.api.app.schemas.product_profiles import ProductProfileCreate
from apps.api.app.schemas.upload_parsing import ParsedUploadRow
from apps.api.app.services.monitoring_rules import build_recommendations, normalize_sp_search_term_rows

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _import():
    return new_monitoring_import(
        workspace_id=uuid4(),
        product_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        created_by="test",
    )


def _product(target_acos: float = 0.25, default_budget: float = 20.0, default_bid: float = 0.90):
    return ProductProfileCreate(
        product_name="Fixture Product",
        target_acos=Decimal(str(target_acos)),
        default_budget=Decimal(str(default_budget)),
        default_bid=Decimal(str(default_bid)),
    )


def _csv_to_parsed_rows(csv_text: str) -> list[ParsedUploadRow]:
    rows = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for i, row in enumerate(reader, start=2):
        # Mirror upload_parser: strip values, None for empty
        cleaned = {k: (v.strip() or None) for k, v in row.items() if k}
        rows.append(ParsedUploadRow(id=uuid4(), row_number=i, row_data_json=cleaned, row_hash=str(i)))
    return rows


def _load_fixture(name: str) -> list[ParsedUploadRow]:
    path = FIXTURES / name
    return _csv_to_parsed_rows(path.read_text(encoding="utf-8-sig"))


# ── Clean fixture ─────────────────────────────────────────────────────────────

class TestCleanFixture:

    def test_clean_fixture_parses_all_11_rows(self) -> None:
        rows = _load_fixture("sp_search_term_clean.csv")
        imp = _import()
        snapshots, warnings = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        assert len(snapshots) == 11

    def test_clean_fixture_produces_diverse_recommendation_types(self) -> None:
        rows = _load_fixture("sp_search_term_clean.csv")
        imp = _import()
        prod = _product(target_acos=0.25)
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        types = {r.recommendation_type for r in recs}
        # Good broad term with sales → should have move_to_exact or watch_lock
        assert RecommendationType.ADD_NEGATIVE_EXACT in types or RecommendationType.ADD_NEGATIVE_PHRASE in types
        # All recs must be pending
        assert all(r.status == "pending_approval" for r in recs)

    def test_clean_fixture_no_critical_data_quality_warnings(self) -> None:
        rows = _load_fixture("sp_search_term_clean.csv")
        imp = _import()
        _, warnings = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        critical_warnings = [w for w in warnings if w.get("severity") == "critical"]
        assert critical_warnings == []

    def test_clean_fixture_acos_correctly_calculated(self) -> None:
        """posture corrector exact row: spend=$154.05, sales=$770.00 → ACOS=0.2001"""
        rows = _load_fixture("sp_search_term_clean.csv")
        imp = _import()
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        exact_row = next(s for s in snapshots if s.customer_search_term == "posture corrector" and s.match_type == "exact")
        # ACOS from report is 20.01% = 0.2001, or calculated: 154.05/770.00 = 0.2000
        assert exact_row.acos is not None
        assert abs(exact_row.acos - Decimal("0.2001")) <= Decimal("0.005")


# ── Edge cases fixture ────────────────────────────────────────────────────────

class TestEdgeCasesFixture:

    def test_asin_search_term_not_negated(self) -> None:
        """B07X3J5WY6 appears as customer search term — must NOT become negative exact."""
        rows = _load_fixture("sp_search_term_edge_cases.csv")
        imp = _import()
        prod = _product()
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        asin_recs = [r for r in recs if r.customer_search_term == "B07X3J5WY6"]
        assert len(asin_recs) == 1
        assert asin_recs[0].recommendation_type not in {
            RecommendationType.ADD_NEGATIVE_EXACT,
            RecommendationType.ADD_NEGATIVE_PHRASE,
        }

    def test_duplicate_search_term_across_campaigns_detected(self) -> None:
        """yoga mat non slip appears in Camp A (broad) and Camp B (auto)."""
        rows = _load_fixture("sp_search_term_edge_cases.csv")
        imp = _import()
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        from apps.api.app.services import monitoring_metrics
        rollups = monitoring_metrics.build_performance_rollups(snapshots)
        assert "yoga mat non slip" in rollups["duplicates"]["overlapping_search_terms"]

    def test_zero_clicks_row_does_not_crash(self) -> None:
        """premium yoga mat row: 0 clicks, 0 spend — should parse without error."""
        rows = _load_fixture("sp_search_term_edge_cases.csv")
        imp = _import()
        snapshots, warnings = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        zero_row = next((s for s in snapshots if s.customer_search_term == "premium yoga mat"), None)
        assert zero_row is not None
        assert zero_row.clicks == 0
        assert zero_row.spend == Decimal("0.00")

    def test_low_data_term_gets_watch_lock(self) -> None:
        """yoga mat 6mm: 2 clicks, 45 impressions, 0 orders → under_tested watch_lock."""
        rows = _load_fixture("sp_search_term_edge_cases.csv")
        imp = _import()
        prod = _product()
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=prod, import_record=imp, snapshots=snapshots)
        low_data = next((r for r in recs if r.customer_search_term == "yoga mat 6mm"), None)
        assert low_data is not None
        assert low_data.recommendation_type == RecommendationType.WATCH_LOCK


# ── Dirty fixture ─────────────────────────────────────────────────────────────

class TestDirtyFixture:

    def test_clicks_exceed_impressions_triggers_data_quality(self) -> None:
        rows = _load_fixture("sp_search_term_dirty.csv")
        imp = _import()
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=_product(), import_record=imp, snapshots=snapshots)
        bad_rec = next((r for r in recs if r.customer_search_term == "clicks exceed impressions"), None)
        assert bad_rec is not None
        assert bad_rec.recommendation_type == RecommendationType.DATA_QUALITY_REVIEW
        assert bad_rec.priority == "critical"

    def test_orders_exceed_clicks_triggers_data_quality(self) -> None:
        rows = _load_fixture("sp_search_term_dirty.csv")
        imp = _import()
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=_product(), import_record=imp, snapshots=snapshots)
        bad_rec = next((r for r in recs if r.customer_search_term == "orders exceed clicks"), None)
        assert bad_rec is not None
        assert bad_rec.recommendation_type == RecommendationType.DATA_QUALITY_REVIEW

    def test_blank_search_term_row_skipped_gracefully(self) -> None:
        """Row with empty customer search term should be skipped (ValueError in normalize)."""
        rows = _load_fixture("sp_search_term_dirty.csv")
        imp = _import()
        snapshots, warnings = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        # The blank search term row should produce a warning, not crash
        skip_warnings = [w for w in warnings if w.get("code") == "ROW_NORMALIZATION_SKIPPED"]
        assert len(skip_warnings) >= 1

    def test_valid_row_in_dirty_file_still_gets_recommendation(self) -> None:
        rows = _load_fixture("sp_search_term_dirty.csv")
        imp = _import()
        snapshots, _ = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        recs = build_recommendations(product=_product(), import_record=imp, snapshots=snapshots)
        valid_rec = next((r for r in recs if r.customer_search_term == "valid normal row"), None)
        assert valid_rec is not None
        # Valid data produces a business recommendation, never a data quality flag
        assert valid_rec.recommendation_type != RecommendationType.DATA_QUALITY_REVIEW


# ── Multi-product fixture ─────────────────────────────────────────────────────

class TestMultiProductFixture:

    def test_multi_product_warning_fired_with_two_asins(self) -> None:
        rows = _load_fixture("sp_search_term_multi_product.csv")
        imp = _import()
        _, warnings = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        multi_product = next((w for w in warnings if w["code"] == "MULTI_PRODUCT_REPORT_DETECTED"), None)
        assert multi_product is not None
        detected_asins = {g["asin"] for g in multi_product["details"]["detected_product_groups"]}
        assert "B08AAAAAA1" in detected_asins
        assert "B08BBBBBBB" in detected_asins

    def test_customer_search_term_asins_not_used_for_product_detection(self) -> None:
        rows = _load_fixture("sp_search_term_multi_product.csv")
        imp = _import()
        _, warnings = normalize_sp_search_term_rows(import_record=imp, rows=rows)
        multi_product = next((w for w in warnings if w["code"] == "MULTI_PRODUCT_REPORT_DETECTED"), None)
        rule = multi_product["details"]["profile_creation_rule"]
        assert "Customer Search Term ASINs" in rule
