"""
Phase 10: Duplicate detection and entity deduplication unit tests.

Tests:
1. Exact duplicate file hash detection
2. Same data fingerprint detection with different filenames
3. Entity key generation (campaign, ad group, product, search term)
4. Recommendation fingerprint calculation
5. Same run duplicate recommendation rejection
"""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.api.app.services.duplicate_detection import (
    DuplicateFileDetectionResult,
    calculate_data_fingerprint,
    calculate_file_hash,
    calculate_recommendation_fingerprint,
    campaign_entity_key,
    ad_group_entity_key,
    product_entity_key,
    search_term_entity_key,
    recommendation_fingerprint_changed,
    can_reuse_import,
    aggregate_entity_metrics,
)
from apps.api.app.schemas.account_imports import (
    AccountImport,
    AccountImportEntity,
    AccountImportStatus,
    DetectionConfidence,
    EntityType,
    ProductResolutionStatus,
    ReportType,
)
from apps.api.app.schemas.uploads import UploadSourceType


# =============================================================================
# Test 1: Exact duplicate file hash detection
# =============================================================================

def test_exact_duplicate_file_hash_same_content():
    """Same content should produce the same SHA-256 hash."""
    content1 = b"this is a test file with some amazon ads data"
    content2 = b"this is a test file with some amazon ads data"
    hash1 = calculate_file_hash(content1)
    hash2 = calculate_file_hash(content2)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 produces 64 hex characters
    assert hash1 == hashlib.sha256(content1).hexdigest()


def test_exact_duplicate_file_hash_different_content():
    """Different content should produce different hashes."""
    content1 = b"report-2024.csv"
    content2 = b"report-2024-v2.csv"
    hash1 = calculate_file_hash(content1)
    hash2 = calculate_file_hash(content2)
    assert hash1 != hash2


# =============================================================================
# Test 2: Same data fingerprint detection with different filenames
# =============================================================================

def test_same_data_different_filename_produces_same_fingerprint():
    """Same business data with different filename should produce same fingerprint."""
    workspace_id = uuid4()
    headers = ["Campaign Name", "Ad Group Name", "Targeting", "Customer Search Term",
               "Impressions", "Clicks", "Spend", "Sales", "Orders"]
    rows = [
        {"Campaign Name": "Campaign A", "Ad Group Name": "AG1", "Targeting": "shoes",
         "Customer Search Term": "running shoes", "Impressions": 1000, "Clicks": 50,
         "Spend": 25.50, "Sales": 150.00, "Orders": 5},
    ]
    
    fp1 = calculate_data_fingerprint(
        workspace_id=workspace_id,
        report_type="sponsored_products_search_term_report",
        sheet_names=["Sheet1"],
        row_count=1,
        headers=headers,
        normalized_rows=rows,
        total_spend=25.50,
        total_sales=150.00,
        total_clicks=50,
        total_orders=5,
        total_impressions=1000,
    )
    
    # Same data, different filename (no filename in fingerprint - that's the point)
    fp2 = calculate_data_fingerprint(
        workspace_id=workspace_id,
        report_type="sponsored_products_search_term_report",
        sheet_names=["Sheet1"],
        row_count=1,
        headers=headers,
        normalized_rows=rows,
        total_spend=25.50,
        total_sales=150.00,
        total_clicks=50,
        total_orders=5,
        total_impressions=1000,
    )
    
    assert fp1 == fp2
    assert len(fp1) == 64


def test_different_data_produces_different_fingerprint():
    """Different business data should produce different fingerprints."""
    workspace_id = uuid4()
    headers = ["Campaign Name", "Ad Group Name", "Targeting", "Customer Search Term",
               "Impressions", "Clicks", "Spend", "Sales", "Orders"]
    rows1 = [
        {"Campaign Name": "Campaign A", "Ad Group Name": "AG1", "Targeting": "shoes",
         "Customer Search Term": "running shoes", "Impressions": 1000, "Clicks": 50,
         "Spend": 25.50, "Sales": 150.00, "Orders": 5},
    ]
    rows2 = [
        {"Campaign Name": "Campaign B", "Ad Group Name": "AG2", "Targeting": "hats",
         "Customer Search Term": "bucket hats", "Impressions": 500, "Clicks": 10,
         "Spend": 5.50, "Sales": 20.00, "Orders": 1},
    ]
    
    fp1 = calculate_data_fingerprint(
        workspace_id=workspace_id,
        report_type="sponsored_products_search_term_report",
        row_count=1,
        headers=headers,
        normalized_rows=rows1,
        total_spend=25.50,
        total_sales=150.00,
    )
    fp2 = calculate_data_fingerprint(
        workspace_id=workspace_id,
        report_type="sponsored_products_search_term_report",
        row_count=1,
        headers=headers,
        normalized_rows=rows2,
        total_spend=5.50,
        total_sales=20.00,
    )
    
    assert fp1 != fp2


# =============================================================================
# Test 3: Entity key generation
# =============================================================================

def test_campaign_entity_key_with_id():
    """Campaign with ID should use the ID as the primary key."""
    key = campaign_entity_key(campaign_id="CAMP123", campaign_name="My Campaign")
    assert key == "campaign_id:CAMP123"


def test_campaign_entity_key_without_id():
    """Campaign without ID should use name and workspace."""
    key = campaign_entity_key(
        campaign_name="My Campaign",
        workspace_id="ws-1",
        marketplace="US"
    )
    assert "my campaign" in key
    assert "ws-1" in key
    assert "US" in key


def test_same_campaign_maps_to_same_key_across_reports():
    """Same campaign name in different reports should produce the same key."""
    key1 = campaign_entity_key(
        campaign_name="Brand_Campaign",
        workspace_id="ws-1",
        marketplace="US"
    )
    key2 = campaign_entity_key(
        campaign_name="brand_campaign",  # Case-insensitive
        workspace_id="ws-1",
        marketplace="US"
    )
    assert key1 == key2


def test_product_entity_key_with_asin():
    """ASIN-based product key should use uppercase ASIN."""
    key = product_entity_key(asin="B00TEST123")
    assert key == "product:asin:B00TEST123"


def test_product_entity_key_with_sku():
    """SKU-based product key."""
    key = product_entity_key(sku="MY-SKU-001")
    assert key == "product:sku:MY-SKU-001"


def test_product_entity_key_with_nothing():
    """Unknown product becomes not_linked."""
    key = product_entity_key(asin=None, sku=None)
    assert key == "product:not_linked"


def test_product_entity_key_asin_takes_precedence():
    """ASIN should take precedence over SKU."""
    key = product_entity_key(asin="B00TEST123", sku="MY-SKU-001")
    assert key == "product:asin:B00TEST123"


def test_search_term_entity_key():
    """Search term key should combine all parts."""
    key = search_term_entity_key(
        campaign_key="campaign:name:ws-1:US:my campaign",
        ad_group_key="ad_group:campaign:name:ws-1:US:my campaign:my ad group",
        targeting="shoes",
        match_type="broad",
        customer_search_term="running shoes",
    )
    assert "running shoes" in key
    assert "shoes" in key
    assert "broad" in key


# =============================================================================
# Test 4: Recommendation fingerprint
# =============================================================================

def test_same_recommendation_produces_same_fingerprint():
    """Same recommendation should produce same fingerprint."""
    fp1 = calculate_recommendation_fingerprint(
        import_id="import-1",
        recommendation_type="increase_bid",
        entity_type="search_term",
        campaign_key="campaign:name:ws-1:US:my campaign",
        ad_group_key="ad_group:campaign:name:ws-1:US:my campaign:ag1",
        search_term="running shoes",
        current_value="0.50",
        recommended_value="0.55",
        rule_name="low_acos_bid_increase",
        agent_id="bid_optimization_agent",
        strategy_profile="conservative",
    )
    fp2 = calculate_recommendation_fingerprint(
        import_id="import-1",
        recommendation_type="increase_bid",
        entity_type="search_term",
        campaign_key="campaign:name:ws-1:US:my campaign",
        ad_group_key="ad_group:campaign:name:ws-1:US:my campaign:ag1",
        search_term="running shoes",
        current_value="0.50",
        recommended_value="0.55",
        rule_name="low_acos_bid_increase",
        agent_id="bid_optimization_agent",
        strategy_profile="conservative",
    )
    assert fp1 == fp2


def test_different_recommendation_produces_different_fingerprint():
    """Different recommendations should have different fingerprints."""
    fp1 = calculate_recommendation_fingerprint(
        import_id="import-1",
        recommendation_type="increase_bid",
        entity_type="search_term",
        campaign_key="campaign:name:ws-1:US:my campaign",
        search_term="running shoes",
        current_value="0.50",
        recommended_value="0.55",
        rule_name="low_acos_bid_increase",
        agent_id="bid_optimization_agent",
        strategy_profile="conservative",
    )
    fp2 = calculate_recommendation_fingerprint(
        import_id="import-1",
        recommendation_type="pause_review",  # Different type
        entity_type="search_term",
        campaign_key="campaign:name:ws-1:US:my campaign",
        search_term="running shoes",
        current_value="0.50",
        recommended_value="0.55",
        rule_name="high_acos_pause",
        agent_id="pause_review_agent",
        strategy_profile="conservative",
    )
    assert fp1 != fp2


def test_recommendation_fingerprint_changed_detection():
    """Should detect when a recommendation fingerprint has changed."""
    fp_v1 = calculate_recommendation_fingerprint(
        import_id="import-1",
        recommendation_type="increase_bid",
        entity_type="search_term",
        campaign_key="key1",
        search_term="test",
        current_value="0.50",
        recommended_value="0.55",
        rule_name="rule1",
        agent_id="agent1",
        strategy_profile="conservative",
    )
    fp_v2 = calculate_recommendation_fingerprint(
        import_id="import-1",
        recommendation_type="increase_bid",
        entity_type="search_term",
        campaign_key="key1",
        search_term="test",
        current_value="0.50",
        recommended_value="0.65",  # Changed value
        rule_name="rule1",
        agent_id="agent1",
        strategy_profile="conservative",
    )
    assert recommendation_fingerprint_changed(fp_v1, fp_v2)


# =============================================================================
# Test 5: Can reuse import
# =============================================================================

def test_can_reuse_import_ready_for_analysis():
    """Import that is ready_for_analysis can be reused."""
    now = datetime.now(UTC)
    import_record = AccountImport(
        id=uuid4(),
        workspace_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        report_type=UploadSourceType.ACCOUNT_BULK_REPORT,
        status=AccountImportStatus.READY_FOR_ANALYSIS,
        detected_report_type=ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT,
        detection_confidence=DetectionConfidence.HIGH,
        total_rows=100,
        processed_rows=100,
        error_rows=0,
        created_by="user-1",
        created_at=now,
        updated_at=now,
    )
    assert can_reuse_import(import_record) is True


def test_cannot_reuse_failed_import():
    """Failed import should not be reusable."""
    now = datetime.now(UTC)
    import_record = AccountImport(
        id=uuid4(),
        workspace_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        report_type=UploadSourceType.ACCOUNT_BULK_REPORT,
        status=AccountImportStatus.FAILED,
        detected_report_type=ReportType.UNKNOWN_REPORT,
        detection_confidence=DetectionConfidence.LOW,
        total_rows=0,
        processed_rows=0,
        error_rows=1,
        created_by="user-1",
        created_at=now,
        updated_at=now,
    )
    assert can_reuse_import(import_record) is False


# =============================================================================
# Test 6: Entity metrics aggregation
# =============================================================================

def test_aggregate_entity_metrics():
    """Should correctly aggregate metrics across entities."""
    now = datetime.now(UTC)
    entities = [
        AccountImportEntity(
            id=uuid4(),
            workspace_id=uuid4(),
            account_import_id=uuid4(),
            entity_type=EntityType.SEARCH_TERM,
            entity_key="key1",
            resolution_status=ProductResolutionStatus.MATCHED_EXISTING_PRODUCT,
            metrics_json={"spend": 10.50, "sales": 50.00, "clicks": 5, "orders": 2, "impressions": 100},
            created_at=now,
        ),
        AccountImportEntity(
            id=uuid4(),
            workspace_id=uuid4(),
            account_import_id=uuid4(),
            entity_type=EntityType.SEARCH_TERM,
            entity_key="key2",
            resolution_status=ProductResolutionStatus.MATCHED_EXISTING_PRODUCT,
            metrics_json={"spend": 15.25, "sales": 100.00, "clicks": 10, "orders": 3, "impressions": 200},
            created_at=now,
        ),
    ]
    aggregated = aggregate_entity_metrics(entities)
    assert aggregated["total_spend"] == pytest.approx(25.75)
    assert aggregated["total_sales"] == pytest.approx(150.00)
    assert aggregated["total_clicks"] == 15
    assert aggregated["total_orders"] == 5
    assert aggregated["total_impressions"] == 300