"""Comprehensive unit tests for SPSearchTermPipeline.

Covers:
  - Schema detection: missing required column, extra-space headers, unknown columns
  - Type coercion: dates, integers, Decimal (currency + percentage)
  - Row validation: all cross-field checks, negative values, date order
  - Edge cases: zero sales (blank ACOS OK), zero clicks (blank CPC OK)
  - Classification: ASIN search term, targeting types
  - Aggregation: correct metric recalculation from raw totals
  - Summary/footer row quarantine
  - Duplicate row detection
  - Mixed currencies flagged in report
  - Full fixture file tests
  - Recommendation gate: blocked on schema error, allowed with warnings
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.app.services.sp_search_term_pipeline import (
    REQUIRED_CANONICAL,
    SP_COLUMN_MAP,
    RowSeverity,
    SPSearchTermPipeline,
    _classify_search_term,
    _classify_targeting,
    _is_summary_row,
    _norm_key,
    _to_date,
    _to_decimal,
    _to_decimal_currency,
    _to_decimal_percent,
    _to_int,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ============================================================
# Helpers
# ============================================================

CANONICAL_HEADERS = [
    "Campaign Name",
    "Ad Group Name",
    "Targeting",
    "Match Type",
    "Customer Search Term",
    "Start Date",
    "End Date",
    "Impressions",
    "Clicks",
    "Click-Thru Rate (CTR)",
    "Cost Per Click (CPC)",
    "Spend",
    "7 Day Total Sales",
    "Total Advertising Cost of Sales (ACOS)",
    "Total Return on Advertising Spend (ROAS)",
    "7 Day Total Orders (#)",
    "7 Day Total Units (#)",
    "7 Day Conversion Rate",
]


def _make_row(**overrides) -> dict:
    base = {
        "Campaign Name": "Test Campaign",
        "Ad Group Name": "Test Group",
        "Targeting": "running shoes",
        "Match Type": "broad",
        "Customer Search Term": "running shoes men",
        "Start Date": "2026-01-01",
        "End Date": "2026-01-07",
        "Impressions": 2000,
        "Clicks": 40,
        "Click-Thru Rate (CTR)": "2.00%",
        "Cost Per Click (CPC)": "$0.90",
        "Spend": "$36.00",
        "7 Day Total Sales": "$144.00",
        "Total Advertising Cost of Sales (ACOS)": "25.00%",
        "Total Return on Advertising Spend (ROAS)": "4.00",
        "7 Day Total Orders (#)": 5,
        "7 Day Total Units (#)": 5,
        "7 Day Conversion Rate": "12.50%",
    }
    base.update(overrides)
    return base


def _parse_fixture(filename: str) -> tuple[list[dict], list[str]]:
    """Read a fixture CSV and return (list_of_row_dicts, header_list)."""
    path = FIXTURES_DIR / filename
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    rows = []
    for r in reader:
        rows.append({k.strip(): (v.strip() if v else v) for k, v in r.items()})
    return rows, headers


def _run_fixture(filename: str):
    rows, headers = _parse_fixture(filename)
    pipeline = SPSearchTermPipeline()
    return pipeline.run(raw_rows=rows, original_headers=headers)


# ============================================================
# Normalization helpers
# ============================================================

class TestNormKey:
    def test_strips_special_chars(self):
        assert _norm_key("Click-Thru Rate (CTR)") == "click thru rate ctr"

    def test_collapses_whitespace(self):
        assert _norm_key("  7 Day   Total Sales  ") == "7 day total sales"

    def test_lowercases(self):
        assert _norm_key("Campaign Name") == "campaign name"

    def test_hash_symbol_becomes_space(self):
        assert _norm_key("7 Day Total Orders (#)") == "7 day total orders"


class TestColumnMap:
    def test_all_canonical_headers_map_correctly(self):
        pipeline = SPSearchTermPipeline()
        schema = pipeline.detect_schema(CANONICAL_HEADERS)
        assert schema.is_valid, f"Missing: {schema.missing_columns}"

    def test_extra_whitespace_headers_still_map(self):
        pipeline = SPSearchTermPipeline()
        padded = [f"  {h}  " for h in CANONICAL_HEADERS]
        schema = pipeline.detect_schema(padded)
        assert schema.is_valid, f"Missing: {schema.missing_columns}"

    def test_missing_required_columns_detected(self):
        headers_without_search_term = [h for h in CANONICAL_HEADERS if "Search Term" not in h]
        pipeline = SPSearchTermPipeline()
        schema = pipeline.detect_schema(headers_without_search_term)
        assert not schema.is_valid
        assert "customer_search_term" in schema.missing_columns

    def test_unknown_columns_collected(self):
        pipeline = SPSearchTermPipeline()
        schema = pipeline.detect_schema(CANONICAL_HEADERS + ["My Custom Column", "Another Unknown"])
        assert "My Custom Column" in schema.unknown_columns
        assert "Another Unknown" in schema.unknown_columns


# ============================================================
# Type coercion
# ============================================================

class TestToDate:
    def test_iso_string(self):
        assert _to_date("2026-01-15") == date(2026, 1, 15)

    def test_date_object_passthrough(self):
        d = date(2026, 5, 1)
        assert _to_date(d) is d

    def test_none_returns_none(self):
        assert _to_date(None) is None

    def test_bad_string_returns_none(self):
        assert _to_date("not a date") is None


class TestToInt:
    def test_integer_passthrough(self):
        assert _to_int(127) == 127

    def test_float_rounds(self):
        assert _to_int(127.9) == 128

    def test_string_number(self):
        assert _to_int("4850") == 4850

    def test_comma_separated_number(self):
        assert _to_int("1,234") == 1234

    def test_none_returns_none(self):
        assert _to_int(None) is None

    def test_empty_string_returns_none(self):
        assert _to_int("") is None


class TestToDecimalCurrency:
    def test_dollar_prefixed_string(self):
        assert _to_decimal_currency("$104.14") == Decimal("104.14")

    def test_euro_prefixed_string(self):
        assert _to_decimal_currency("€99.50") == Decimal("99.50")

    def test_plain_number(self):
        assert _to_decimal_currency(104.14) == Decimal("104.14")

    def test_zero_dollar(self):
        assert _to_decimal_currency("$0.00") == Decimal("0.00")

    def test_none_returns_none(self):
        assert _to_decimal_currency(None) is None

    def test_empty_string_returns_none(self):
        assert _to_decimal_currency("") is None


class TestToDecimalPercent:
    def test_percent_string_csv(self):
        assert _to_decimal_percent("14.17%") == Decimal("0.1417")

    def test_zero_percent_string(self):
        assert _to_decimal_percent("0.00%") == Decimal("0.00")

    def test_xlsx_fraction_float(self):
        # XLSX stores 14.17% as 0.1417
        result = _to_decimal_percent(0.1417)
        assert result == Decimal("0.1417")

    def test_none_returns_none(self):
        assert _to_decimal_percent(None) is None

    def test_empty_string_returns_none(self):
        assert _to_decimal_percent("") is None


# ============================================================
# Search term and targeting classification
# ============================================================

class TestClassifySearchTerm:
    def test_valid_asin(self):
        assert _classify_search_term("B08N5WRWNW") == "asin"

    def test_numeric_asin(self):
        assert _classify_search_term("0123456789") == "asin"

    def test_keyword_not_asin(self):
        assert _classify_search_term("running shoes men") == "keyword"

    def test_partial_asin_is_keyword(self):
        assert _classify_search_term("B0INVALID") == "keyword"

    def test_none_returns_none(self):
        assert _classify_search_term(None) is None


class TestClassifyTargeting:
    def test_auto_star(self):
        assert _classify_targeting("*", "auto") == "auto"

    def test_auto_keyword(self):
        assert _classify_targeting("auto", None) == "auto"

    def test_close_match(self):
        assert _classify_targeting("Close match", None) == "auto"

    def test_asin_prefix(self):
        assert _classify_targeting("asin=B08N5WRWNW", "exact") == "product_asin"

    def test_asin_colon_prefix(self):
        assert _classify_targeting("asin:B08N5WRWNW", "exact") == "product_asin"

    def test_direct_asin(self):
        assert _classify_targeting("B08N5WRWNW", "exact") == "product_asin"

    def test_category(self):
        assert _classify_targeting("category=12345678", None) == "category"

    def test_keyword_broad(self):
        assert _classify_targeting("running shoes", "broad") == "keyword"

    def test_keyword_exact(self):
        assert _classify_targeting("running shoes", "exact") == "keyword"

    # --- Real-data patterns from SP Search Term XLSX exports ---

    def test_close_match_hyphenated(self):
        # Amazon exports "close-match" (hyphenated) in XLSX; must be "auto"
        assert _classify_targeting("close-match", "-") == "auto"

    def test_loose_match_hyphenated(self):
        assert _classify_targeting("loose-match", "-") == "auto"

    def test_keyword_group_auto(self):
        # keyword-group="..." is Amazon's auto keyword-group targeting
        assert _classify_targeting('keyword-group="Keywords related to your product category"', "-") == "auto"

    def test_keyword_group_brand_auto(self):
        assert _classify_targeting('keyword-group="keywords related to your brand"', "-") == "auto"

    def test_asin_expanded_is_product_asin(self):
        assert _classify_targeting('asin-expanded="B0C695MY8G"', "-") == "product_asin"

    def test_price_category_compound(self):
        # Compound targeting: price filter + category — the "category=" token takes precedence
        assert _classify_targeting('price>10.0 category="Die-Cut Tools & Accessories"', "-") == "category"

    def test_asin_quoted_is_product_asin(self):
        # Real data: asin="b076z4n4dp" (lowercase ASIN in quotes)
        assert _classify_targeting('asin="b076z4n4dp"', "-") == "product_asin"


# ============================================================
# Row validation: good path
# ============================================================

class TestValidRowGoodPath:
    def test_clean_row_has_no_issues(self):
        pipeline = SPSearchTermPipeline()
        _, _, report = pipeline.run(
            raw_rows=[_make_row()],
            original_headers=CANONICAL_HEADERS,
        )
        assert report.valid_rows == 1
        assert report.error_rows == 0
        assert report.warning_rows == 0
        assert report.quarantined_rows == 0
        assert report.schema_valid is True
        assert report.can_generate_recommendations is True

    def test_date_range_extracted(self):
        rows = [
            _make_row(**{"Start Date": "2026-01-01", "End Date": "2026-01-07"}),
            _make_row(**{"Start Date": "2026-01-08", "End Date": "2026-01-14", "Customer Search Term": "shoes men"}),
        ]
        _, _, report = SPSearchTermPipeline().run(raw_rows=rows, original_headers=CANONICAL_HEADERS)
        assert report.date_range_start == date(2026, 1, 1)
        assert report.date_range_end == date(2026, 1, 14)


# ============================================================
# Row validation: errors
# ============================================================

class TestValidationErrors:
    def test_negative_spend_is_error(self):
        pipeline = SPSearchTermPipeline()
        validated, _, _ = pipeline.run(
            raw_rows=[_make_row(**{"Spend": "$-15.00"})],
            original_headers=CANONICAL_HEADERS,
        )
        codes = {i.code for i in validated[0].issues}
        assert "NEGATIVE_VALUE" in codes
        assert validated[0].effective_severity == RowSeverity.ERROR

    def test_negative_impressions_is_error(self):
        pipeline = SPSearchTermPipeline()
        validated, _, _ = pipeline.run(
            raw_rows=[_make_row(**{"Impressions": -100})],
            original_headers=CANONICAL_HEADERS,
        )
        codes = {i.code for i in validated[0].issues}
        assert "NEGATIVE_VALUE" in codes

    def test_wrong_date_order_is_error(self):
        pipeline = SPSearchTermPipeline()
        validated, _, _ = pipeline.run(
            raw_rows=[_make_row(**{"Start Date": "2026-01-14", "End Date": "2026-01-07"})],
            original_headers=CANONICAL_HEADERS,
        )
        codes = {i.code for i in validated[0].issues}
        assert "DATE_ORDER_INVALID" in codes
        assert validated[0].effective_severity == RowSeverity.ERROR


class TestValidationWarnings:
    def test_clicks_exceed_impressions_is_warning(self):
        row = _make_row(**{
            "Impressions": 10,
            "Clicks": 25,
            "Click-Thru Rate (CTR)": "250.00%",
            "Spend": "$20.00",
            "Cost Per Click (CPC)": "$0.80",
        })
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        codes = {i.code for i in validated[0].issues}
        assert "CLICKS_EXCEED_IMPRESSIONS" in codes
        assert validated[0].effective_severity == RowSeverity.WARNING

    def test_ctr_mismatch_is_warning(self):
        # Clicks/impressions = 40/2000 = 2%, but reported CTR = 5%
        row = _make_row(**{"Click-Thru Rate (CTR)": "5.00%"})
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        codes = {i.code for i in validated[0].issues}
        assert "CTR_MISMATCH" in codes

    def test_acos_mismatch_is_warning(self):
        # spend=$36, sales=$144 → ACOS=25%, reported 50%
        row = _make_row(**{"Total Advertising Cost of Sales (ACOS)": "50.00%"})
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        codes = {i.code for i in validated[0].issues}
        assert "ACOS_MISMATCH" in codes

    def test_cpc_mismatch_is_warning(self):
        # spend=$36, clicks=40 → CPC=$0.90, reported $2.50
        row = _make_row(**{"Cost Per Click (CPC)": "$2.50"})
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        codes = {i.code for i in validated[0].issues}
        assert "CPC_MISMATCH" in codes

    def test_roas_mismatch_is_warning(self):
        # sales=$144, spend=$36 → ROAS=4.00, reported 1.00
        row = _make_row(**{"Total Return on Advertising Spend (ROAS)": "1.00"})
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        codes = {i.code for i in validated[0].issues}
        assert "ROAS_MISMATCH" in codes

    def test_cvr_mismatch_is_warning(self):
        # orders=5, clicks=40 → CVR=12.5%, reported 50%
        row = _make_row(**{"7 Day Conversion Rate": "50.00%"})
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        codes = {i.code for i in validated[0].issues}
        assert "CVR_MISMATCH" in codes


# ============================================================
# Zero-value edge cases (must NOT raise errors)
# ============================================================

class TestZeroValueEdgeCases:
    def test_zero_sales_blank_acos_not_error(self):
        """ACOS being None when sales=0 is expected and must not error."""
        row = _make_row(**{
            "7 Day Total Sales": "$0.00",
            "7 Day Total Orders (#)": 0,
            "7 Day Total Units (#)": 0,
            "7 Day Conversion Rate": "0.00%",
            "Total Advertising Cost of Sales (ACOS)": "",
            "Total Return on Advertising Spend (ROAS)": "0.00",
        })
        validated, _, report = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        codes = {i.code for i in validated[0].issues}
        assert "ACOS_MISMATCH" not in codes
        assert validated[0].effective_severity in (RowSeverity.OK, RowSeverity.WARNING)

    def test_zero_clicks_blank_cpc_not_error(self):
        """CPC being None when clicks=0 is expected and must not error."""
        row = _make_row(**{
            "Clicks": 0,
            "Click-Thru Rate (CTR)": "0.00%",
            "Cost Per Click (CPC)": "",
            "Spend": "$0.00",
            "7 Day Total Sales": "$0.00",
            "7 Day Total Orders (#)": 0,
            "7 Day Total Units (#)": 0,
            "7 Day Conversion Rate": "0.00%",
            "Total Advertising Cost of Sales (ACOS)": "",
            "Total Return on Advertising Spend (ROAS)": "0.00",
        })
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        codes = {i.code for i in validated[0].issues}
        assert "CPC_MISMATCH" not in codes
        assert "NEGATIVE_VALUE" not in codes

    def test_zero_impressions_row_no_ctr_check(self):
        """CTR check should be skipped when impressions=0."""
        row = _make_row(**{
            "Impressions": 0,
            "Clicks": 0,
            "Click-Thru Rate (CTR)": "0.00%",
            "Cost Per Click (CPC)": "",
            "Spend": "$0.00",
            "7 Day Total Sales": "$0.00",
            "7 Day Total Orders (#)": 0,
            "7 Day Total Units (#)": 0,
            "7 Day Conversion Rate": "0.00%",
            "Total Advertising Cost of Sales (ACOS)": "",
            "Total Return on Advertising Spend (ROAS)": "0.00",
        })
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        codes = {i.code for i in validated[0].issues}
        assert "CTR_MISMATCH" not in codes


# ============================================================
# Quarantine
# ============================================================

class TestQuarantine:
    def test_summary_row_quarantined(self):
        row = _make_row(**{"Campaign Name": "Total"})
        validated, _, report = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        assert validated[0].is_quarantined
        assert report.quarantined_rows == 1

    def test_missing_search_term_quarantined(self):
        row = _make_row(**{"Customer Search Term": ""})
        validated, _, report = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        assert validated[0].is_quarantined

    def test_missing_campaign_name_quarantined(self):
        row = _make_row(**{"Campaign Name": ""})
        validated, _, report = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        assert validated[0].is_quarantined


# ============================================================
# Duplicate detection
# ============================================================

class TestDuplicateDetection:
    def test_duplicate_row_flagged_as_warning(self):
        row = _make_row()
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[row, row], original_headers=CANONICAL_HEADERS
        )
        codes_row2 = {i.code for i in validated[1].issues}
        assert "DUPLICATE_ROW" in codes_row2
        assert validated[1].effective_severity == RowSeverity.WARNING

    def test_non_duplicate_rows_no_warning(self):
        r1 = _make_row()
        r2 = _make_row(**{"Customer Search Term": "running shoes women"})
        validated, _, _ = SPSearchTermPipeline().run(
            raw_rows=[r1, r2], original_headers=CANONICAL_HEADERS
        )
        for vr in validated:
            codes = {i.code for i in vr.issues}
            assert "DUPLICATE_ROW" not in codes


# ============================================================
# Schema validation gate
# ============================================================

class TestRecommendationGate:
    def test_missing_required_col_blocks_recommendations(self):
        """Schema error from missing column must block recommendation generation."""
        headers_no_search_term = [h for h in CANONICAL_HEADERS if "Search Term" not in h]
        rows = [_make_row()]
        # Remove the customer_search_term key from each row too
        for row in rows:
            row.pop("Customer Search Term", None)
        _, _, report = SPSearchTermPipeline().run(
            raw_rows=rows, original_headers=headers_no_search_term
        )
        assert report.schema_valid is False
        assert report.can_generate_recommendations is False

    def test_row_warnings_do_not_block_recommendations(self):
        """Warnings must NOT block recommendations — only schema errors do."""
        rows = [
            _make_row(**{"Click-Thru Rate (CTR)": "5.00%"}),  # CTR_MISMATCH warning
        ]
        _, _, report = SPSearchTermPipeline().run(
            raw_rows=rows, original_headers=CANONICAL_HEADERS
        )
        assert report.warning_rows >= 1
        assert report.can_generate_recommendations is True

    def test_all_quarantined_blocks_recommendations(self):
        rows = [_make_row(**{"Campaign Name": "Total"})]  # quarantined
        _, _, report = SPSearchTermPipeline().run(
            raw_rows=rows, original_headers=CANONICAL_HEADERS
        )
        assert report.can_generate_recommendations is False


# ============================================================
# Aggregation
# ============================================================

class TestAggregation:
    def test_aggregates_multiple_rows_same_key(self):
        r1 = _make_row(**{"Start Date": "2026-01-01", "End Date": "2026-01-07"})
        r2 = _make_row(**{
            "Start Date": "2026-01-08",
            "End Date": "2026-01-14",
            "Impressions": 3000,
            "Clicks": 60,
            "Click-Thru Rate (CTR)": "2.00%",
            "Spend": "$54.00",
            "7 Day Total Sales": "$216.00",
            "7 Day Total Orders (#)": 7,
            "7 Day Total Units (#)": 7,
            "7 Day Conversion Rate": "11.67%",
            "Total Advertising Cost of Sales (ACOS)": "25.00%",
            "Total Return on Advertising Spend (ROAS)": "4.00",
        })
        _, aggregated, _ = SPSearchTermPipeline().run(
            raw_rows=[r1, r2], original_headers=CANONICAL_HEADERS
        )
        assert len(aggregated) == 1
        agg = aggregated[0]
        assert agg.total_impressions == 5000
        assert agg.total_clicks == 100
        assert agg.total_spend == Decimal("90.00")
        assert agg.total_sales == Decimal("360.00")
        assert agg.total_orders == 12

    def test_agg_ctr_from_totals(self):
        r1 = _make_row(**{"Impressions": 1000, "Clicks": 20})
        r2 = _make_row(**{
            "Impressions": 3000, "Clicks": 30,
            "Customer Search Term": "running shoes women",
        })
        _, aggregated, _ = SPSearchTermPipeline().run(
            raw_rows=[r1, r2], original_headers=CANONICAL_HEADERS
        )
        # 2 distinct search terms → 2 aggregated rows
        total_imp = sum(a.total_impressions for a in aggregated)
        total_clk = sum(a.total_clicks for a in aggregated)
        # Each row aggregated separately; check each CTR = clicks/impressions
        for agg in aggregated:
            if agg.total_impressions > 0:
                expected_ctr = Decimal(agg.total_clicks) / Decimal(agg.total_impressions)
                assert agg.agg_ctr == expected_ctr

    def test_agg_acos_none_when_no_sales(self):
        row = _make_row(**{
            "7 Day Total Sales": "$0.00",
            "7 Day Total Orders (#)": 0,
            "7 Day Total Units (#)": 0,
            "7 Day Conversion Rate": "0.00%",
            "Total Advertising Cost of Sales (ACOS)": "",
            "Total Return on Advertising Spend (ROAS)": "0.00",
        })
        _, aggregated, _ = SPSearchTermPipeline().run(
            raw_rows=[row], original_headers=CANONICAL_HEADERS
        )
        assert aggregated[0].agg_acos is None

    def test_distinct_keys_produce_separate_aggregated_rows(self):
        r1 = _make_row()
        r2 = _make_row(**{"Customer Search Term": "running shoes women"})
        r3 = _make_row(**{"Match Type": "exact"})
        _, aggregated, _ = SPSearchTermPipeline().run(
            raw_rows=[r1, r2, r3], original_headers=CANONICAL_HEADERS
        )
        assert len(aggregated) == 3

    def test_quarantined_rows_excluded_from_aggregation(self):
        good = _make_row()
        quarantined = _make_row(**{"Campaign Name": "Total"})
        _, aggregated, _ = SPSearchTermPipeline().run(
            raw_rows=[good, quarantined], original_headers=CANONICAL_HEADERS
        )
        # Only the good row contributes to aggregation
        assert len(aggregated) == 1


# ============================================================
# Fixture file tests
# ============================================================

class TestFixtureMissingRequiredColumn:
    def test_missing_customer_search_term_schema_invalid(self):
        _, _, report = _run_fixture("sp_st_missing_required_col.csv")
        assert report.schema_valid is False
        assert "customer_search_term" in report.missing_columns
        assert report.can_generate_recommendations is False


class TestFixtureExtraSpaceHeaders:
    def test_extra_space_headers_normalize_correctly(self):
        _, _, report = _run_fixture("sp_st_extra_spaces_headers.csv")
        assert report.schema_valid is True, f"Missing cols: {report.missing_columns}"
        assert report.total_rows == 2


class TestFixtureZeroSalesBlankAcos:
    def test_no_acos_error_when_sales_zero(self):
        validated, _, report = _run_fixture("sp_st_zero_sales_blank_acos.csv")
        for vr in validated:
            codes = {i.code for i in vr.issues}
            assert "ACOS_MISMATCH" not in codes, f"Row {vr.normalized.row_number}: unexpected ACOS_MISMATCH"

    def test_report_has_no_error_rows(self):
        _, _, report = _run_fixture("sp_st_zero_sales_blank_acos.csv")
        assert report.error_rows == 0


class TestFixtureZeroClicksBlankCpc:
    def test_no_cpc_error_when_clicks_zero(self):
        validated, _, _ = _run_fixture("sp_st_zero_clicks_blank_cpc.csv")
        for vr in validated:
            codes = {i.code for i in vr.issues}
            assert "CPC_MISMATCH" not in codes, f"Row {vr.normalized.row_number}: unexpected CPC_MISMATCH"

    def test_no_negative_errors(self):
        _, _, report = _run_fixture("sp_st_zero_clicks_blank_cpc.csv")
        assert report.error_rows == 0


class TestFixtureWrongDateOrder:
    def test_bad_date_order_row_is_error(self):
        validated, _, report = _run_fixture("sp_st_wrong_date_order.csv")
        date_errors = [
            vr for vr in validated
            if any(i.code == "DATE_ORDER_INVALID" for i in vr.issues)
        ]
        assert len(date_errors) == 1
        assert date_errors[0].normalized.customer_search_term == "bad row end before start"

    def test_good_rows_still_valid(self):
        validated, _, _ = _run_fixture("sp_st_wrong_date_order.csv")
        good_rows = [
            vr for vr in validated
            if vr.effective_severity == RowSeverity.OK
        ]
        assert len(good_rows) >= 2


class TestFixtureNegativeSpend:
    def test_negative_spend_is_error(self):
        validated, _, report = _run_fixture("sp_st_negative_spend.csv")
        neg_spend_errors = [
            vr for vr in validated
            if any(i.code == "NEGATIVE_VALUE" and i.field == "spend" for i in vr.issues)
        ]
        assert len(neg_spend_errors) >= 1

    def test_negative_impressions_is_error(self):
        validated, _, _ = _run_fixture("sp_st_negative_spend.csv")
        neg_imp_errors = [
            vr for vr in validated
            if any(i.code == "NEGATIVE_VALUE" and i.field == "impressions" for i in vr.issues)
        ]
        assert len(neg_imp_errors) >= 1


class TestFixtureDuplicateRows:
    def test_duplicate_rows_flagged_as_warning(self):
        validated, _, _ = _run_fixture("sp_st_duplicate_rows.csv")
        dup_warnings = [
            vr for vr in validated
            if any(i.code == "DUPLICATE_ROW" for i in vr.issues)
        ]
        assert len(dup_warnings) >= 2  # rows 2 and 4 are dupes of row 1

    def test_no_error_rows_from_duplicates(self):
        _, _, report = _run_fixture("sp_st_duplicate_rows.csv")
        assert report.error_rows == 0


class TestFixtureMixedCurrencies:
    def test_mixed_currencies_reported(self):
        _, _, report = _run_fixture("sp_st_mixed_currencies.csv")
        mixed_issues = [i for i in report.top_issues if i["code"] == "MIXED_CURRENCIES"]
        assert len(mixed_issues) == 1

    def test_currency_is_none_when_mixed(self):
        _, _, report = _run_fixture("sp_st_mixed_currencies.csv")
        assert report.currency is None


class TestFixtureMalformedAsin:
    def test_valid_asin_search_term_classified(self):
        validated, _, _ = _run_fixture("sp_st_malformed_asin.csv")
        asin_rows = [
            vr for vr in validated
            if vr.normalized.search_term_type == "asin"
        ]
        assert len(asin_rows) >= 1

    def test_non_asin_patterns_are_keywords(self):
        validated, _, _ = _run_fixture("sp_st_malformed_asin.csv")
        keyword_rows = [
            vr for vr in validated
            if vr.normalized.search_term_type == "keyword"
        ]
        assert len(keyword_rows) >= 2  # "B0INVALID123", "NOTANASIN", "supplement for athletes"


class TestFixtureSummaryFooter:
    def test_total_row_quarantined(self):
        validated, _, report = _run_fixture("sp_st_summary_footer.csv")
        quarantined = [vr for vr in validated if vr.is_quarantined]
        assert len(quarantined) == 1
        assert quarantined[0].normalized.campaign_name.lower() == "total"

    def test_real_rows_not_quarantined(self):
        validated, _, _ = _run_fixture("sp_st_summary_footer.csv")
        real_rows = [vr for vr in validated if not vr.is_quarantined]
        assert len(real_rows) == 3

    def test_aggregation_excludes_summary_row(self):
        _, aggregated, _ = _run_fixture("sp_st_summary_footer.csv")
        # All 3 real rows have distinct search terms → 3 aggregated rows
        assert len(aggregated) == 3


class TestFixtureRealTargetingPatterns:
    """Integration test covering all real-data targeting patterns from XLSX exports."""

    def test_schema_valid(self):
        _, _, report = _run_fixture("sp_st_real_targeting_patterns.csv")
        assert report.schema_valid is True, f"Missing: {report.missing_columns}"

    def test_no_error_rows(self):
        _, _, report = _run_fixture("sp_st_real_targeting_patterns.csv")
        assert report.error_rows == 0

    def test_close_match_hyphenated_classified_auto(self):
        validated, _, _ = _run_fixture("sp_st_real_targeting_patterns.csv")
        row = next(vr for vr in validated if (vr.normalized.targeting or "") == "close-match")
        assert row.normalized.targeting_type == "auto"

    def test_loose_match_hyphenated_classified_auto(self):
        validated, _, _ = _run_fixture("sp_st_real_targeting_patterns.csv")
        row = next(vr for vr in validated if (vr.normalized.targeting or "") == "loose-match")
        assert row.normalized.targeting_type == "auto"

    def test_keyword_group_classified_auto(self):
        validated, _, _ = _run_fixture("sp_st_real_targeting_patterns.csv")
        kg_rows = [vr for vr in validated if (vr.normalized.targeting or "").startswith("keyword-group=")]
        assert len(kg_rows) == 2
        for vr in kg_rows:
            assert vr.normalized.targeting_type == "auto", f"Expected auto, got {vr.normalized.targeting_type}"

    def test_price_category_compound_classified_category(self):
        validated, _, _ = _run_fixture("sp_st_real_targeting_patterns.csv")
        row = next(vr for vr in validated if "price>10.0" in (vr.normalized.targeting or ""))
        assert row.normalized.targeting_type == "category"

    def test_asin_expanded_classified_product_asin(self):
        validated, _, _ = _run_fixture("sp_st_real_targeting_patterns.csv")
        row = next(vr for vr in validated if (vr.normalized.targeting or "").startswith("asin-expanded="))
        assert row.normalized.targeting_type == "product_asin"

    def test_manual_keyword_rows_classified_keyword(self):
        validated, _, _ = _run_fixture("sp_st_real_targeting_patterns.csv")
        kw_rows = [vr for vr in validated if (vr.normalized.match_type or "").upper() in ("BROAD", "EXACT")]
        assert len(kw_rows) == 2
        for vr in kw_rows:
            assert vr.normalized.targeting_type == "keyword"


class TestFixtureCleanData:
    def test_clean_fixture_all_valid(self):
        _, _, report = _run_fixture("sp_search_term_clean.csv")
        assert report.schema_valid is True
        assert report.error_rows == 0
        assert report.total_rows == report.valid_rows + report.warning_rows

    def test_clean_fixture_date_range(self):
        _, _, report = _run_fixture("sp_search_term_clean.csv")
        assert report.date_range_start == date(2026, 1, 1)
        assert report.date_range_end == date(2026, 1, 7)

    def test_clean_fixture_agg_metrics_from_totals(self):
        """Verify aggregated CTR = total_clicks / total_impressions, not average of row CTRs."""
        _, aggregated, _ = _run_fixture("sp_search_term_clean.csv")
        for agg in aggregated:
            if agg.total_impressions > 0:
                expected_ctr = Decimal(agg.total_clicks) / Decimal(agg.total_impressions)
                assert agg.agg_ctr == expected_ctr, (
                    f"{agg.customer_search_term}: CTR {agg.agg_ctr} ≠ {expected_ctr}"
                )


class TestFixtureDirtyData:
    def test_dirty_fixture_clicks_exceed_impressions_warning(self):
        validated, _, _ = _run_fixture("sp_search_term_dirty.csv")
        cei_warnings = [
            vr for vr in validated
            if any(i.code == "CLICKS_EXCEED_IMPRESSIONS" for i in vr.issues)
        ]
        assert len(cei_warnings) >= 1

    def test_missing_search_term_quarantined(self):
        validated, _, _ = _run_fixture("sp_search_term_dirty.csv")
        quarantined = [vr for vr in validated if vr.is_quarantined]
        assert len(quarantined) >= 1


# ============================================================
# Validation report fields
# ============================================================

class TestValidationReport:
    def test_report_counts_match_row_list(self):
        rows = [
            _make_row(),                                                  # valid
            _make_row(**{"Customer Search Term": "shoes women"}),         # valid (different key)
            _make_row(**{"Click-Thru Rate (CTR)": "50.00%"}),             # warning (CTR mismatch)
            _make_row(**{"Spend": "$-5.00"}),                             # error (negative)
            _make_row(**{"Campaign Name": "Total"}),                      # quarantined
        ]
        validated, _, report = SPSearchTermPipeline().run(
            raw_rows=rows, original_headers=CANONICAL_HEADERS
        )
        assert report.total_rows == 5
        assert report.quarantined_rows == 1
        total = report.valid_rows + report.warning_rows + report.error_rows + report.quarantined_rows
        assert total == 5

    def test_top_issues_sorted_by_count(self):
        rows = [
            _make_row(**{"Click-Thru Rate (CTR)": "50.00%"}),
            _make_row(**{"Click-Thru Rate (CTR)": "50.00%", "Customer Search Term": "shoes women"}),
        ]
        _, _, report = SPSearchTermPipeline().run(
            raw_rows=rows, original_headers=CANONICAL_HEADERS
        )
        if len(report.top_issues) >= 2:
            assert report.top_issues[0]["count"] >= report.top_issues[1]["count"]

    def test_missing_columns_in_report(self):
        headers_without_spend = [h for h in CANONICAL_HEADERS if h != "Spend"]
        rows = [_make_row()]
        _, _, report = SPSearchTermPipeline().run(
            raw_rows=rows, original_headers=headers_without_spend
        )
        assert "spend" in report.missing_columns
