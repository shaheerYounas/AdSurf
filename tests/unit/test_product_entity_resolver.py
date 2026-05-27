from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from apps.api.app.schemas.account_imports import (
    AccountImport,
    AccountImportStatus,
    DetectionConfidence,
    EntityType,
    ProductResolutionStatus,
    ReportType,
)
from apps.api.app.schemas.product_profiles import ProductProfile
from apps.api.app.schemas.upload_parsing import ParsedUploadRow
from apps.api.app.schemas.uploads import UploadSourceType
from apps.api.app.services.product_entity_resolver import ProductEntityResolver


def test_resolver_groups_account_import_rows_by_product_and_entities() -> None:
    workspace_id = uuid4()
    product_id = uuid4()
    now = datetime.now(UTC)
    product = ProductProfile(
        id=product_id,
        workspace_id=workspace_id,
        product_name="Existing Shoe",
        asin="B0TESTASIN",
        sku="SHOE-1",
        marketplace="US",
        currency="USD",
        target_acos=Decimal("0.5000"),
        default_budget=Decimal("10.0000"),
        default_bid=Decimal("1.0000"),
        status="active",
        created_at=now,
        updated_at=now,
    )
    import_record = AccountImport(
        id=uuid4(),
        workspace_id=workspace_id,
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        report_type=UploadSourceType.ACCOUNT_BULK_REPORT,
        status=AccountImportStatus.READY_FOR_ANALYSIS,
        detected_report_type=ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT,
        detection_confidence=DetectionConfidence.HIGH,
        created_by="system",
        created_at=now,
        updated_at=now,
    )
    rows = [
        _row(
            1,
            {
                "ASIN": "B0TESTASIN",
                "SKU": "SHOE-1",
                "Product": "Existing Shoe",
                "Campaign Name": "Campaign A",
                "Ad Group Name": "Ad Group A",
                "Targeting": "running shoes",
                "Customer Search Term": "blue running shoes",
                "Impressions": "100",
                "Clicks": "12",
                "Spend": "24.50",
                "7 Day Total Sales": "80",
                "7 Day Total Orders": "2",
            },
        ),
        _row(
            2,
            {
                "ASIN": "B0NEWASIN1",
                "SKU": "NEW-1",
                "Product": "New Hat",
                "Campaign Name": "Campaign B",
                "Ad Group Name": "Ad Group B",
                "Targeting": "sun hat",
                "Customer Search Term": "wide brim hat",
                "Impressions": "50",
                "Clicks": "10",
                "Spend": "15",
                "7 Day Total Sales": "0",
                "7 Day Total Orders": "0",
            },
        ),
    ]

    result = ProductEntityResolver().resolve(import_record=import_record, rows=rows, existing_products=[product])

    assert any(entity.entity_type == EntityType.ACCOUNT and entity.metrics_json["spend"] == "39.5000" for entity in result.entities)
    assert any(entity.product_id == product_id and entity.resolution_status == ProductResolutionStatus.MATCHED_EXISTING_PRODUCT for entity in result.entities)
    assert any(entity.entity_type == EntityType.SEARCH_TERM and entity.customer_search_term == "wide brim hat" for entity in result.entities)
    assert len(result.product_mapping_suggestions) == 1
    assert result.product_mapping_suggestions[0].asin == "B0NEWASIN1"


def _row(row_number: int, data: dict) -> ParsedUploadRow:
    return ParsedUploadRow(row_number=row_number, row_data_json=data, row_hash=f"hash-{row_number}")
