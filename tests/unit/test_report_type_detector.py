from apps.api.app.schemas.account_imports import DetectionConfidence, EntityType, ReportType
from apps.api.app.services.report_type_detector import ReportTypeDetector


def test_detects_sponsored_products_search_term_report() -> None:
    result = ReportTypeDetector().detect(
        headers=[
            "Customer Search Term",
            "Targeting",
            "Campaign Name",
            "Ad Group Name",
            "Spend",
            "7 Day Total Sales",
            "7 Day Total Orders",
            "ASIN",
            "SKU",
        ]
    )

    assert result.detected_report_type == ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT
    assert result.confidence == DetectionConfidence.HIGH
    assert result.required_columns_present is True
    assert result.missing_columns == []
    assert EntityType.PRODUCT in result.available_entity_levels
    assert EntityType.SEARCH_TERM in result.available_entity_levels
    assert result.product_identifiers_available == ["asin", "sku"]


def test_detects_bulk_sheet() -> None:
    result = ReportTypeDetector().detect(
        headers=[
            "Product",
            "Entity",
            "Operation",
            "Campaign ID",
            "Ad Group ID",
            "Portfolio ID",
            "SKU",
            "ASIN",
            "Bid",
            "Budget",
        ]
    )

    assert result.detected_report_type == ReportType.BULK_SHEET
    assert result.confidence == DetectionConfidence.HIGH
    assert result.required_columns_present is True
    assert result.product_identifiers_available == ["asin", "sku", "product_name"]


def test_detects_bulk_sheet_with_aliased_columns() -> None:
    """Bulk sheet detection should work with 'Daily Budget' aliased to 'budget'."""
    result = ReportTypeDetector().detect(
        headers=[
            "Product",
            "Entity",
            "Operation",
            "Campaign ID",
            "Ad Group ID",
            "Portfolio ID",
            "SKU",
            "ASIN (Informational only)",
            "Ad Group Default Bid",
            "Daily Budget",
        ]
    )

    assert result.detected_report_type == ReportType.BULK_SHEET
    assert result.confidence == DetectionConfidence.HIGH
    assert result.required_columns_present is True


def test_detects_bulk_sheet_with_info_suffix() -> None:
    """Bulk sheet with '(Informational only)' column suffixes should still detect."""
    result = ReportTypeDetector().detect(
        headers=[
            "Product",
            "Entity",
            "Operation",
            "Campaign ID",
            "Ad Group ID",
            "Portfolio ID",
            "SKU",
            "ASIN (Informational only)",
            "Campaign Name (Informational only)",
            "Ad Group Name (Informational only)",
            "Bid",
            "Daily Budget",
        ]
    )

    assert result.detected_report_type == ReportType.BULK_SHEET
    assert result.required_columns_present is True


def test_bulk_sheet_missing_single_column_is_rejected() -> None:
    """When one required column is missing, detection falls to unknown with no missing context."""
    result = ReportTypeDetector().detect(
        headers=[
            "Product",
            "Entity",
            "Operation",
            "Campaign ID",
            "Ad Group ID",
            "Portfolio ID",
            "SKU",
            "ASIN",
            "Bid",
            # "Budget" is missing
        ]
    )

    assert result.detected_report_type == ReportType.UNKNOWN_REPORT
    assert result.required_columns_present is False


def test_search_term_report_with_real_headers() -> None:
    """Full Amazon SP search term report headers should be detected."""
    result = ReportTypeDetector().detect(
        headers=[
            "Start Date",
            "End Date",
            "Portfolio name",
            "Currency",
            "Campaign Name",
            "Ad Group Name",
            "Retailer",
            "Country",
            "Targeting",
            "Match Type",
            "Customer Search Term",
            "Impressions",
            "Clicks",
            "Click-Thru Rate (CTR)",
            "Cost Per Click (CPC)",
            "Spend",
            "7 Day Total Sales ",
            "Total Advertising Cost of Sales (ACOS) ",
            "Total Return on Advertising Spend (ROAS)",
            "7 Day Total Orders (#)",
            "7 Day Total Units (#)",
            "7 Day Conversion Rate",
            "7 Day Advertised SKU Units (#)",
            "7 Day Other SKU Units (#)",
            "7 Day Advertised SKU Sales ",
            "7 Day Other SKU Sales ",
        ]
    )

    assert result.detected_report_type == ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT
    assert result.confidence == DetectionConfidence.HIGH
    assert result.required_columns_present is True


def test_unknown_report_on_unrecognizable_headers() -> None:
    result = ReportTypeDetector().detect(headers=["Column A", "Column B", "Column C"])
    assert result.detected_report_type == ReportType.UNKNOWN_REPORT
    assert result.required_columns_present is False


def test_daily_budget_aliases_to_budget() -> None:
    """'Daily Budget' should be recognized as 'budget' for bulk detection."""
    headers = [
        "Product", "Entity", "Operation", "Campaign ID", "Ad Group ID",
        "Portfolio ID", "SKU", "ASIN", "Bid", "Daily Budget",
    ]
    result = ReportTypeDetector().detect(headers=headers)
    assert result.detected_report_type == ReportType.BULK_SHEET
    assert "budget" not in result.missing_columns


def test_ad_group_default_bid_aliases_to_bid() -> None:
    """'Ad Group Default Bid' should be recognized as 'bid'."""
    headers = [
        "Product", "Entity", "Operation", "Campaign ID", "Ad Group ID",
        "Portfolio ID", "SKU", "ASIN", "Ad Group Default Bid", "Budget",
    ]
    result = ReportTypeDetector().detect(headers=headers)
    assert result.detected_report_type == ReportType.BULK_SHEET
    assert "bid" not in result.missing_columns


def test_unknown_report_returns_missing_context_safely() -> None:
    result = ReportTypeDetector().detect(headers=["Some Column", "Other Column"])

    assert result.detected_report_type == ReportType.UNKNOWN_REPORT
    assert result.confidence == DetectionConfidence.LOW
    assert result.required_columns_present is False
    assert result.available_entity_levels == [EntityType.ACCOUNT]
