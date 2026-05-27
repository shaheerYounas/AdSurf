from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.api.app.schemas.uploads import UploadSourceType


class ReportType(StrEnum):
    SINGLE_PRODUCT_REPORT = "single_product_report"
    ACCOUNT_BULK_REPORT = "account_bulk_report"
    SPONSORED_PRODUCTS_SEARCH_TERM_REPORT = "sponsored_products_search_term_report"
    SPONSORED_PRODUCTS_TARGETING_REPORT = "sponsored_products_targeting_report"
    SPONSORED_PRODUCTS_CAMPAIGN_REPORT = "sponsored_products_campaign_report"
    BULK_SHEET = "bulk_sheet"
    UNKNOWN_REPORT = "unknown_report"


class DetectionConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EntityType(StrEnum):
    ACCOUNT = "account"
    PRODUCT = "product"
    CAMPAIGN = "campaign"
    AD_GROUP = "ad_group"
    TARGET = "target"
    SEARCH_TERM = "search_term"


class ProductResolutionStatus(StrEnum):
    MATCHED_EXISTING_PRODUCT = "matched_existing_product"
    SUGGESTED_NEW_PRODUCT = "suggested_new_product"
    UNKNOWN_PRODUCT = "unknown_product"
    NEEDS_USER_MAPPING = "needs_user_mapping"


class ProductMappingSuggestionStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MANUALLY_MAPPED = "manually_mapped"


class AccountImportStatus(StrEnum):
    DETECTED = "detected"
    NEEDS_MAPPING = "needs_mapping"
    READY_FOR_ANALYSIS = "ready_for_analysis"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ReportDetectionResult(BaseModel):
    detected_report_type: ReportType
    confidence: DetectionConfidence
    required_columns_present: bool
    missing_columns: list[str] = Field(default_factory=list)
    available_entity_levels: list[EntityType] = Field(default_factory=list)
    product_identifiers_available: list[str] = Field(default_factory=list)


class AccountImportCreateRequest(BaseModel):
    upload_id: UUID


class AccountImport(BaseModel):
    id: UUID
    workspace_id: UUID
    upload_id: UUID
    parse_run_id: UUID
    report_type: UploadSourceType
    status: AccountImportStatus
    detected_report_type: ReportType
    detection_confidence: DetectionConfidence
    total_rows: int = 0
    processed_rows: int = 0
    error_rows: int = 0
    data_quality_warnings_json: list[dict] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AccountImportEntity(BaseModel):
    id: UUID
    workspace_id: UUID
    account_import_id: UUID
    product_id: UUID | None = None
    asin: str | None = None
    sku: str | None = None
    product_name: str | None = None
    campaign_name: str | None = None
    ad_group_name: str | None = None
    targeting: str | None = None
    customer_search_term: str | None = None
    entity_type: EntityType
    entity_key: str
    resolution_status: ProductResolutionStatus
    metrics_json: dict = Field(default_factory=dict)
    raw_row_refs_json: list[int] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductMappingSuggestion(BaseModel):
    id: UUID
    workspace_id: UUID
    account_import_id: UUID
    asin: str | None = None
    sku: str | None = None
    detected_product_name: str | None = None
    suggested_product_id: UUID | None = None
    status: ProductMappingSuggestionStatus = ProductMappingSuggestionStatus.PENDING
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountImportResponse(BaseModel):
    import_record: AccountImport
    detection: ReportDetectionResult
    entities: list[AccountImportEntity]
    product_mapping_suggestions: list[ProductMappingSuggestion]
