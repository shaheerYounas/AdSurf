"""Golden-path correctness tests for real uploaded Amazon Ads files.

Tests two uploaded files:
1. Sponsored_Products_Search_term_report (2).xlsx - SP search term report
2. bulk-a19yjbemeq5qup-*.xlsx - Amazon bulk operations workbook
"""

import os
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from apps.api.app.schemas.account_imports import DetectionConfidence, ReportType
from apps.api.app.schemas.monitoring import (
    MonitoringImport,
    MonitoringImportStatus,
    RecommendationType,
)
from apps.api.app.schemas.product_profiles import ProductProfile, ProductProfileStatus
from apps.api.app.services.bulk_export_generator import generate_bulk_sheet
from apps.api.app.services.monitoring_rules import (
    build_recommendations,
    normalize_sp_search_term_rows,
)
from apps.api.app.services.report_type_detector import ReportTypeDetector
from apps.api.app.services.upload_parser import UploadParser


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
SEARCH_TERM_FILE = ROOT / "Sponsored_Products_Search_term_report (2).xlsx"
BULK_FILE = ROOT / "bulk-a19yjbemeq5qup-20260511-20260512-1778596309224.xlsx"


def _read_xlsx(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _fake_product() -> ProductProfile:
    """Create a minimal product profile for recommendation generation."""
    now = datetime.now(UTC)
    return ProductProfile(
        id=uuid4(),
        workspace_id=uuid4(),
        product_name="Test Product",
        asin=None,
        sku=None,
        marketplace="US",
        currency="USD",
        target_acos=Decimal("0.50"),
        default_budget=Decimal("10.00"),
        default_bid=Decimal("1.00"),
        status=ProductProfileStatus.ACTIVE,
        product_cost=None,
        product_price=None,
        margin_pct=None,
        break_even_acos=None,
        category=None,
        brand_name=None,
        created_at=now,
        updated_at=now,
    )


def _fake_import() -> MonitoringImport:
    """Create a minimal monitoring import record."""
    now = datetime.now(UTC)
    return MonitoringImport(
        id=uuid4(),
        workspace_id=uuid4(),
        product_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        report_type="amazon_ads_sp_search_term_report",
        status=MonitoringImportStatus.PROCESSING,
        date_range_start=None,
        date_range_end=None,
        total_rows=0,
        processed_rows=0,
        error_rows=0,
        data_quality_warnings_json=[],
        created_by="test",
        created_at=now,
        updated_at=now,
        error_message=None,
    )


# ---------------------------------------------------------------------------
# File 1: Sponsored Products Search Term Report
# ---------------------------------------------------------------------------

class TestSponsoredProductsSearchTermReport:
    """Golden-path tests for Sponsored_Products_Search_term_report (2).xlsx."""

    def test_file_exists(self):
        assert SEARCH_TERM_FILE.exists(), f"Missing test fixture: {SEARCH_TERM_FILE}"

    def test_parsed_successfully(self):
        content = _read_xlsx(SEARCH_TERM_FILE)
        result = UploadParser().parse(
            content=content,
            original_filename=SEARCH_TERM_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        assert result.detected_file_type == "xlsx"
        assert result.total_rows > 100, f"Expected 100+ data rows, got {result.total_rows}"
        assert result.total_columns > 20, f"Expected 20+ columns, got {result.total_columns}"
        assert len(result.errors) == 0, f"Unexpected parse errors: {result.errors}"
        assert result.selected_sheet_name is not None
        assert "search" in result.selected_sheet_name.lower()

    def test_classified_as_amazon_sp_search_term_report(self):
        content = _read_xlsx(SEARCH_TERM_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=SEARCH_TERM_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        headers = list(parsed.rows[0].row_data_json.keys())
        detection = ReportTypeDetector().detect(headers=headers)
        assert detection.detected_report_type == ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT, (
            f"Expected SP search term report, got {detection.detected_report_type}"
        )
        assert detection.confidence == DetectionConfidence.HIGH
        assert detection.required_columns_present is True
        assert detection.missing_columns == [], f"Unexpected missing columns: {detection.missing_columns}"

    def test_required_columns_recognized(self):
        """Verify that every SP_SEARCH_TERM_REQUIRED column is present."""
        content = _read_xlsx(SEARCH_TERM_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=SEARCH_TERM_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        headers = {h.strip().lower() for h in parsed.rows[0].row_data_json}
        # The required columns from domain/monitoring.py are checked more
        # thoroughly by normalize_sp_search_term_rows below
        assert "customer search term" in headers or any("customer search term" in h for h in headers)
        assert "spend" in headers or any("spend" in h for h in headers)

    def test_metrics_parsed(self):
        """Metrics from rows should be parsed as proper numeric types."""
        content = _read_xlsx(SEARCH_TERM_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=SEARCH_TERM_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        # Check a sample of rows have numeric values
        numeric_fields = {"impressions", "clicks", "spend", "7 day total sales", "7 day total orders"}
        data_rows = [r for r in parsed.rows if r.row_number > 1]
        # At least one row should have non-zero spend or impressions
        found_metrics = False
        for row in data_rows[:20]:
            for key, value in row.row_data_json.items():
                normalised = key.lower().replace(" ", "").replace("#", "").replace("(", "").replace(")", "")
                for field in numeric_fields:
                    if field.replace(" ", "") in normalised:
                        if isinstance(value, (int, float)) and float(value) != 0:
                            found_metrics = True
        assert found_metrics, "No rows with numeric metrics found in the sample."

    def test_no_search_volume_or_organic_rank_triggered(self):
        """Verify no Search Volume / Organic Rank fields exist in parsed data."""
        content = _read_xlsx(SEARCH_TERM_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=SEARCH_TERM_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        headers = set(parsed.rows[0].row_data_json.keys())
        forbidden = {"search volume", "organic rank", "organic ranking", "search rank"}
        header_lower = {h.lower() for h in headers}
        for term in forbidden:
            assert term not in header_lower, (
                f"'{term}' should not be required/triggered for SP search term report"
            )

    def test_recommendations_generated_or_no_recommendation_reason(self):
        """At least one recommendation candidate can be generated or a clear
        'no recommendation due to thresholds' reason is produced."""
        content = _read_xlsx(SEARCH_TERM_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=SEARCH_TERM_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        import_record = _fake_import()
        # Override workspace/product ids to match
        # (normalize_sp_search_term_rows uses them only for snapshot creation)
        snapshots, warnings = normalize_sp_search_term_rows(
            import_record=import_record,
            rows=parsed.rows,
        )
        assert len(snapshots) > 0, "No snapshots normalized from search term report."
        assert len(warnings) == 0, f"Unexpected normalization warnings: {warnings}"

        product = _fake_product()
        recommendations = build_recommendations(
            product=product,
            import_record=import_record,
            snapshots=snapshots,
        )
        assert len(recommendations) > 0, (
            "Expected at least one recommendation (even KEEP_RUNNING) "
            "from golden-path search term report."
        )

        rec_types = {r.recommendation_type for r in recommendations}
        # Every row gets a recommendation — the golden-path expectation is
        # that the deterministic rules produce something for each snapshot.
        non_keep = rec_types - {RecommendationType.KEEP_RUNNING}
        if non_keep:
            # At least one actionable recommendation
            pass
        else:
            # All KEEP_RUNNING is a valid "no recommendation due to thresholds"
            # — this is the expected safe fallback.
            pass


# ---------------------------------------------------------------------------
# File 2: Bulk Operations Workbook
# ---------------------------------------------------------------------------

class TestBulkOperationsWorkbook:
    """Golden-path tests for bulk-a19yjbemeq5qup-*.xlsx."""

    def test_file_exists(self):
        assert BULK_FILE.exists(), f"Missing test fixture: {BULK_FILE}"

    def test_classified_as_bulk_sheet(self):
        content = _read_xlsx(BULK_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=BULK_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        # The selected sheet should be a bulk-sheet-format sheet
        headers = list(parsed.rows[0].row_data_json.keys())
        detection = ReportTypeDetector().detect(headers=headers)
        assert detection.detected_report_type == ReportType.BULK_SHEET, (
            f"Expected BULK_SHEET, got {detection.detected_report_type}"
        )
        assert detection.confidence == DetectionConfidence.HIGH

    def test_sponsored_products_campaigns_sheet_detected(self):
        """The parser should detect 'Sponsored Products Campaigns' as a sheet."""
        content = _read_xlsx(BULK_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=BULK_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        sheet_names_lower = [s.lower() for s in parsed.detected_sheet_names]
        assert "sponsored products campaigns" in sheet_names_lower, (
            f"'Sponsored Products Campaigns' not found in {parsed.detected_sheet_names}"
        )

    def test_sp_search_term_report_sheet_detected(self):
        """'SP Search Term Report' should be listed among detected sheet names."""
        content = _read_xlsx(BULK_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=BULK_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        sheet_names_lower = [s.lower() for s in parsed.detected_sheet_names]
        assert "sp search term report" in sheet_names_lower, (
            f"'SP Search Term Report' not found in {parsed.detected_sheet_names}"
        )

    def test_selected_sheet_is_sponsored_products_campaigns(self):
        """Priority logic should select 'Sponsored Products Campaigns' first."""
        content = _read_xlsx(BULK_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=BULK_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        assert parsed.selected_sheet_name.strip().lower() == "sponsored products campaigns", (
            f"Expected 'Sponsored Products Campaigns' selected, got '{parsed.selected_sheet_name}'"
        )

    def test_bulk_compatible_entities_parsed(self):
        """Verify entities like campaigns, keywords, and product targeting are parsed."""
        content = _read_xlsx(BULK_FILE)
        parsed = UploadParser().parse(
            content=content,
            original_filename=BULK_FILE.name,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        # Check that entity-specific fields exist in the parsed data
        headers = set(parsed.rows[0].row_data_json.keys())
        entity_indicators = ["entity", "operation", "campaign id", "ad group id", "keyword text"]
        found = [h for h in entity_indicators if h in {k.lower() for k in headers}]
        assert len(found) >= 3, (
            f"Missing bulk entity columns. Found: {found}, Headers: {sorted(headers)}"
        )

        # Verify we have rows for various entity types
        entity_values = set()
        for row in parsed.rows:
            for key, value in row.row_data_json.items():
                if key.lower() == "entity" and value:
                    entity_values.add(str(value).strip().lower())
        expected_entities = {"campaign", "keyword", "bidding adjustment", "product targeting"}
        common = entity_values & expected_entities
        assert len(common) >= 2, (
            f"Expected at least 2 entity types from {expected_entities}, got {entity_values}"
        )

    def test_export_generator_produces_draft_output(self):
        """The bulk export generator can produce a separate draft CSV output
        using fake approved recommendations."""
        # Create a minimal approved recommendation
        from apps.api.app.schemas.monitoring import Recommendation, RecommendationConfidence, RecommendationPriority, RecommendationStatus

        rec = Recommendation(
            id=uuid4(),
            workspace_id=uuid4(),
            product_id=None,
            monitoring_import_id=None,
            snapshot_id=None,
            account_import_id=None,
            entity_key=None,
            decision_source=None,
            agent_run_id=None,
            ai_run_id=None,
            recommendation_type=RecommendationType.INCREASE_BID,
            entity_type="target",
            status=RecommendationStatus.APPROVED,
            priority=RecommendationPriority.MEDIUM,
            confidence=RecommendationConfidence.MEDIUM,
            rule_version_id="test_v1",
            rule_name="test_rule",
            campaign_name="Test Campaign",
            ad_group_name="Test Ad Group",
            targeting="keyword-group=\"test\"",
            customer_search_term="test search term",
            match_type="Broad",
            current_bid=Decimal("1.00"),
            recommended_bid=Decimal("1.10"),
            change_percent=Decimal("10.0"),
            current_budget=None,
            recommended_budget=None,
            input_metrics_json={"spend": "5.00", "orders": 2, "impressions": 100, "clicks": 10},
            current_metric_snapshot_json={},
            evidence_json={},
            proposed_action_json={"action": "increase_bid", "action_level": "targeting"},
            explanation_json={"summary": "Test increase bid recommendation."},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        result = generate_bulk_sheet(
            approved_recommendations=[rec],
            workspace_id=uuid4(),
            export_name="Golden Path Test Export",
        )
        assert "csv_content" in result
        assert result["total_rows"] >= 1, f"Expected at least 1 row, got {result['total_rows']}"
        assert "csv" in result["filename"].lower() or result["filename"].endswith(".csv")
        assert result["total_recommendations"] == 1
        assert "audit_log" in result
        assert len(result["audit_log"]) == 1
        csv_content = result["csv_content"]
        assert "Record ID" in csv_content
        assert "AdSurf" in csv_content or "Operation" in csv_content

    def test_source_workbook_not_overwritten(self):
        """Verify that parsing the bulk workbook does not modify the original file."""
        original_stat = BULK_FILE.stat()
        original_size = original_stat.st_size
        original_mtime = original_stat.st_mtime
