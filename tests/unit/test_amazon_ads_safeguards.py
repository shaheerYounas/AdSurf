from apps.api.app.schemas.account_imports import DetectionConfidence, ReportDetectionResult, ReportType
from apps.api.app.services.amazon_ads_safeguards import analyze_search_term_report_rows


def test_safeguards_flag_zero_sales_spend_asins_metric_mismatch_and_duplicates() -> None:
    detection = _search_term_detection()
    rows = [
        {
            "_row_number": 2,
            "Currency": "USD",
            "Country": "United States",
            "Retailer": "Amazon",
            "Campaign Name": "Auto",
            "Ad Group Name": "A",
            "Targeting": "substitutes",
            "Match Type": "-",
            "Customer Search Term": "b076z4n4dp",
            "Impressions": 100,
            "Clicks": 10,
            "Spend": "5",
            "7 Day Total Sales": "0",
            "Total Advertising Cost of Sales (ACOS)": "0%",
            "Total Return on Advertising Spend (ROAS)": "1",
            "7 Day Total Orders (#)": 0,
        },
        {
            "_row_number": 3,
            "Currency": "USD",
            "Country": "United States",
            "Retailer": "Amazon",
            "Campaign Name": "Manual",
            "Ad Group Name": "B",
            "Targeting": "diamond painting",
            "Match Type": "exact",
            "Customer Search Term": "b076z4n4dp",
            "Impressions": 100,
            "Clicks": 5,
            "Spend": "10",
            "7 Day Total Sales": "20",
            "Total Return on Advertising Spend (ROAS)": "2",
            "7 Day Total Orders (#)": 1,
        },
    ]

    result = analyze_search_term_report_rows(rows=rows, detection=detection)
    codes = {warning["code"] for warning in result.warnings}

    assert "SPEND_WITH_NO_SALES" not in codes
    assert "ACOS_PRESENT_WITH_ZERO_SALES" in codes
    assert next(warning for warning in result.warnings if warning["code"] == "ACOS_PRESENT_WITH_ZERO_SALES")["severity"] == "warning"
    assert "ASIN_SEARCH_TERM" in codes
    assert "AUTO_OR_PRODUCT_TARGETING_CONTEXT" in codes
    assert "MATCH_TYPE_UNSPECIFIED" in codes
    assert "DUPLICATE_SEARCH_TERM_CONTEXTS" in codes


def test_safeguards_flag_currency_marketplace_other_sku_and_mixed_windows() -> None:
    detection = _search_term_detection()
    rows = [
        {
            "Currency": "GBP",
            "Country": "United Kingdom",
            "Retailer": "Amazon",
            "Campaign Name": "C",
            "Ad Group Name": "A",
            "Targeting": "keyword",
            "Match Type": "phrase",
            "Customer Search Term": "diamond tools",
            "Impressions": 100,
            "Clicks": 20,
            "Spend": "50",
            "7 Day Total Sales": "60",
            "7 Day Advertised SKU Sales": "5",
            "7 Day Other SKU Sales": "55",
            "14 Day Total Orders (#)": 2,
            "7 Day Total Units (#)": 3,
        }
    ]

    result = analyze_search_term_report_rows(rows=rows, detection=detection)
    codes = {warning["code"] for warning in result.warnings}

    assert "CURRENCY_MISMATCH" in codes
    assert "MARKETPLACE_MISMATCH" in codes
    assert "OTHER_SKU_SALES_DOMINATE" in codes
    assert "ORDERS_UNITS_DIVERGE" in codes
    assert "MIXED_ATTRIBUTION_WINDOWS" in codes


def test_safeguards_flag_header_aliases_numeric_percent_dates_and_duplicate_rows() -> None:
    detection = _search_term_detection()
    duplicated_row = {
        " Start Date ": "2026-05-10",
        "End Date": "2026-05-01",
        "Campaign Name": "Manual",
        "Ad Group Name": "A",
        "Targeting": "diamond painting",
        "Match Type": "phrase",
        "Search Term": "diamond tools",
        "Impressions": "not-a-number",
        "Clicks": "10",
        "Spend": "5",
        "7 Day Total Sales": "10",
        "Total Advertising Cost of Sales (ACOS)": "25",
        "Clickthru Rate (CTR)": "abc",
        "7 Day Total Orders (#)": "1",
    }
    rows = [
        {**duplicated_row, "_row_number": 2},
        {**duplicated_row, "_row_number": 3},
    ]

    result = analyze_search_term_report_rows(rows=rows, detection=detection)
    codes = {warning["code"] for warning in result.warnings}

    assert "HEADER_HIDDEN_SPACES_NORMALIZED" in codes
    assert "COLUMN_NAME_ALIASES_NORMALIZED" in codes
    assert next(warning for warning in result.warnings if warning["code"] == "COLUMN_NAME_ALIASES_NORMALIZED")["severity"] == "info"
    assert "NUMERIC_COLUMN_NOT_NUMERIC" in codes
    assert "PERCENT_COLUMN_NOT_NUMERIC" in codes
    assert "PERCENT_FORMAT_AMBIGUOUS" in codes
    assert "DATE_RANGE_INVALID" in codes
    assert "DUPLICATE_REPORT_ROWS" in codes


def test_safeguards_flag_mixed_asin_keyword_terms_and_overall_low_data() -> None:
    detection = _search_term_detection()
    rows = [
        {
            "_row_number": 2,
            "Campaign Name": "Auto",
            "Ad Group Name": "A",
            "Targeting": "keyword",
            "Match Type": "broad",
            "Customer Search Term": "b076z4n4dp",
            "Impressions": 20,
            "Clicks": 1,
            "Spend": "0.50",
            "7 Day Total Sales": "0",
            "7 Day Total Orders (#)": 0,
        },
        {
            "_row_number": 3,
            "Campaign Name": "Manual",
            "Ad Group Name": "A",
            "Targeting": "diamond painting",
            "Match Type": "exact",
            "Customer Search Term": "diamond painting kit",
            "Impressions": 30,
            "Clicks": 2,
            "Spend": "1.00",
            "7 Day Total Sales": "0",
            "7 Day Total Orders (#)": 0,
        },
    ]

    result = analyze_search_term_report_rows(rows=rows, detection=detection)
    codes = {warning["code"] for warning in result.warnings}

    assert "ASIN_SEARCH_TERM" in codes
    assert "MIXED_ASIN_AND_KEYWORD_SEARCH_TERMS" in codes
    assert "BLANK_ACOS_WITH_ZERO_SALES_HANDLED" not in codes
    assert "OPTIMIZATION_DATA_INSUFFICIENT" in codes
    assert next(warning for warning in result.warnings if warning["code"] == "NOT_ENOUGH_DATA")["severity"] == "info"


def _search_term_detection() -> ReportDetectionResult:
    return ReportDetectionResult(
        detected_report_type=ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT,
        confidence=DetectionConfidence.HIGH,
        required_columns_present=True,
        missing_columns=[],
        available_entity_levels=[],
        product_identifiers_available=[],
    )
