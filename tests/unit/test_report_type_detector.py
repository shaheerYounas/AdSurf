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


def test_unknown_report_returns_missing_context_safely() -> None:
    result = ReportTypeDetector().detect(headers=["Some Column", "Other Column"])

    assert result.detected_report_type == ReportType.UNKNOWN_REPORT
    assert result.confidence == DetectionConfidence.LOW
    assert result.required_columns_present is False
    assert result.available_entity_levels == [EntityType.ACCOUNT]
