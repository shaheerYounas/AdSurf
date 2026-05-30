"""
Duplicate detection service for uploads, data fingerprints, and recommendations.

Handles:
- Exact file hash duplicate detection (SHA-256)
- Normalized business data fingerprint detection
- Recommendation fingerprint for deduplication
- Entity key deduplication helpers
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from uuid import UUID

from apps.api.app.schemas.account_imports import AccountImport, AccountImportEntity, EntityType
from apps.api.app.schemas.uploads import UploadRecord, UploadSourceType
from apps.api.app.schemas.monitoring import Recommendation
from apps.api.app.schemas.workflows import AgentWorkflow


@dataclass
class DuplicateFileDetectionResult:
    is_duplicate: bool
    duplicate_type: str  # "exact_file_duplicate" or "same_data_duplicate" or "none"
    previous_upload_id: UUID | None = None
    previous_import_id: UUID | None = None
    previous_filename: str | None = None
    uploaded_at: datetime | None = None
    report_type: str | None = None
    date_range: dict | None = None
    row_count: int | None = None
    previous_run_count: int = 0
    recommendation_count: int = 0
    approval_summary: dict | None = None


@dataclass
class DuplicateDataDetectionResult:
    is_duplicate: bool
    data_fingerprint: str
    previous_import_id: UUID | None = None
    previous_upload_id: UUID | None = None
    previous_filename: str | None = None
    imported_at: datetime | None = None
    report_type: str | None = None
    row_count: int | None = None
    previous_run_count: int = 0
    recommendation_count: int = 0
    approval_summary: dict | None = None


# =============================================================================
# Phase 2: Exact Duplicate File Detection
# =============================================================================


def calculate_file_hash(content: bytes) -> str:
    """Calculate SHA-256 hash of raw file content."""
    return hashlib.sha256(content).hexdigest()


def file_hash_matches(existing: UploadRecord, content_hash: str) -> bool:
    """Check if an existing upload has the same file hash."""
    return getattr(existing, "file_hash", None) == content_hash


# =============================================================================
# Phase 3: Data Fingerprint Detection
# =============================================================================


def calculate_data_fingerprint(
    *,
    workspace_id: UUID,
    report_type: str,
    sheet_names: list[str] | None = None,
    row_count: int,
    headers: list[str],
    normalized_rows: list[dict],
    total_spend: float | None = None,
    total_sales: float | None = None,
    total_clicks: int | None = None,
    total_orders: int | None = None,
    total_impressions: int | None = None,
) -> str:
    """
    Calculate a normalized business data fingerprint.

    This fingerprint is designed to detect when the same business data
    is uploaded under a different filename or with different metadata.
    Only business-relevant data is included; random Excel metadata is excluded.
    """
    parts: list[str] = []

    # Workspace scope
    parts.append(f"ws:{workspace_id}")

    # Report type
    parts.append(f"rt:{report_type}")

    # Sheet names (sorted for stability)
    if sheet_names:
        parts.append(f"sn:{','.join(sorted(sheet_names))}")

    # Row count
    parts.append(f"rc:{row_count}")

    # Header columns (sorted for stability)
    sorted_headers = sorted([h.strip().lower() for h in headers])
    parts.append(f"hd:{','.join(sorted_headers[:50])}")

    # Key aggregate metrics
    if total_spend is not None:
        parts.append(f"sp:{total_spend:.2f}")
    if total_sales is not None:
        parts.append(f"sa:{total_sales:.2f}")
    if total_clicks is not None:
        parts.append(f"cl:{total_clicks}")
    if total_orders is not None:
        parts.append(f"or:{total_orders}")
    if total_impressions is not None:
        parts.append(f"im:{total_impressions}")

    # Hash of first 100 normalized rows (key columns only)
    key_columns = _get_key_columns(sorted_headers)
    if key_columns:
        row_hashes = []
        for row in normalized_rows[:100]:
            row_str = "|".join(
                str(row.get(col, "")).strip().lower() for col in key_columns if col in row
            )
            if row_str:
                row_hashes.append(row_str)
        if row_hashes:
            combined = "||".join(row_hashes)
            parts.append(f"rh:{hashlib.sha256(combined.encode('utf-8')).hexdigest()}")

    fingerprint_raw = "|".join(parts)
    return hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest()


def _get_key_columns(headers: list[str]) -> list[str]:
    """Identify key business columns for row-level fingerprinting."""
    key_patterns = [
        "campaign name", "campaign",
        "ad group name", "ad group",
        "targeting", "keyword", "keyword text",
        "customer search term", "search term", "query",
        "asin", "sku",
        "start date", "end date",
    ]
    key_columns = []
    for header in headers:
        h_lower = header.strip().lower()
        for pattern in key_patterns:
            if pattern in h_lower and header not in key_columns:
                key_columns.append(header)
                break
    return key_columns[:10]  # Limit to avoid overly large fingerprints


# =============================================================================
# Phase 4: Entity Key Generation
# =============================================================================


def campaign_entity_key(
    *,
    campaign_id: str | None = None,
    campaign_name: str | None = None,
    workspace_id: str | None = None,
    marketplace: str | None = None,
) -> str:
    """Generate a stable campaign entity key."""
    if campaign_id:
        return f"campaign_id:{campaign_id.strip()}"
    name = (campaign_name or "").strip().lower()
    if not name:
        return "campaign:unknown"
    if marketplace:
        return f"campaign:name:{workspace_id}:{marketplace}:{name}" if workspace_id else f"campaign:name:{name}"
    return f"campaign:name:{workspace_id}:{name}" if workspace_id else f"campaign:name:{name}"


def ad_group_entity_key(
    *,
    ad_group_id: str | None = None,
    ad_group_name: str | None = None,
    campaign_key: str = "",
) -> str:
    """Generate a stable ad group entity key."""
    if ad_group_id:
        return f"ad_group_id:{ad_group_id.strip()}"
    name = (ad_group_name or "").strip().lower()
    return f"ad_group:{campaign_key}:{name}" if name else f"ad_group:{campaign_key}:unknown"


def product_entity_key(
    *,
    asin: str | None = None,
    sku: str | None = None,
) -> str:
    """Generate a stable product entity key."""
    if asin and asin.strip():
        return f"product:asin:{asin.strip().upper()}"
    if sku and sku.strip():
        return f"product:sku:{sku.strip()}"
    return "product:not_linked"


def search_term_entity_key(
    *,
    campaign_key: str = "",
    ad_group_key: str = "",
    targeting: str | None = None,
    match_type: str | None = None,
    customer_search_term: str | None = None,
) -> str:
    """Generate a stable search term entity key."""
    parts = [
        campaign_key,
        ad_group_key,
        (targeting or "").strip().lower(),
        (match_type or "").strip().lower(),
        (customer_search_term or "").strip().lower(),
    ]
    return f"search_term:{'|'.join(parts)}"


# =============================================================================
# Phase 6: Recommendation Fingerprint
# =============================================================================


def calculate_recommendation_fingerprint(
    *,
    import_id: str,
    recommendation_type: str,
    entity_type: str,
    campaign_key: str = "",
    ad_group_key: str = "",
    target_key: str = "",
    search_term: str = "",
    current_value: str | None = None,
    recommended_value: str | None = None,
    rule_name: str = "",
    agent_id: str = "",
    strategy_profile: str = "",
) -> str:
    """
    Calculate a deterministic fingerprint for a recommendation.

    Two recommendations with the same fingerprint are considered duplicates.
    This prevents showing duplicate approval cards for the same action.
    """
    parts = [
        f"import:{import_id}",
        f"type:{recommendation_type}",
        f"entity:{entity_type}",
        f"campaign:{campaign_key}",
        f"adgroup:{ad_group_key}",
        f"target:{target_key}",
        f"term:{search_term.strip().lower()}",
        f"current:{current_value or ''}",
        f"recommend:{recommended_value or ''}",
        f"rule:{rule_name}",
        f"agent:{agent_id}",
        f"strategy:{strategy_profile}",
    ]
    fingerprint_raw = "|".join(parts)
    return hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest()


def recommendation_fingerprint_changed(previous_fingerprint: str, new_fingerprint: str) -> bool:
    """Check if a recommendation fingerprint has changed between runs."""
    return previous_fingerprint != new_fingerprint


# =============================================================================
# Phase 5: Same Data Reuse Helpers
# =============================================================================


def can_reuse_import(existing_import: AccountImport) -> bool:
    """Check if an existing import can be reused for a new analysis run."""
    reusable_statuses = {"ready_for_analysis", "succeeded", "processing"}
    return existing_import.status in reusable_statuses


# =============================================================================
# Metric Aggregation for Fingerprints
# =============================================================================


def aggregate_entity_metrics(entities: list[AccountImportEntity]) -> dict:
    """Aggregate metrics across all entities for fingerprinting."""
    total_spend = Decimal("0")
    total_sales = Decimal("0")
    total_clicks = 0
    total_orders = 0
    total_impressions = 0

    for entity in entities:
        metrics = entity.metrics_json if isinstance(entity.metrics_json, dict) else {}
        try:
            total_spend += Decimal(str(metrics.get("spend", 0)))
        except Exception:
            pass
        try:
            total_sales += Decimal(str(metrics.get("sales", 0)))
        except Exception:
            pass
        try:
            total_clicks += int(metrics.get("clicks", 0))
        except Exception:
            pass
        try:
            total_orders += int(metrics.get("orders", 0))
        except Exception:
            pass
        try:
            total_impressions += int(metrics.get("impressions", 0))
        except Exception:
            pass

    return {
        "total_spend": float(total_spend),
        "total_sales": float(total_sales),
        "total_clicks": total_clicks,
        "total_orders": total_orders,
        "total_impressions": total_impressions,
    }