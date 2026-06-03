from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UploadStatus(StrEnum):
    INITIALIZED = "initialized"
    UPLOADED = "uploaded"
    QUEUED_FOR_PROCESSING = "queued_for_processing"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class UploadSourceType(StrEnum):
    COMPETITOR_KEYWORD_RESEARCH = "competitor_keyword_research"
    AMAZON_ADS_SP_SEARCH_TERM_REPORT = "amazon_ads_sp_search_term_report"
    SINGLE_PRODUCT_REPORT = "single_product_report"
    ACCOUNT_BULK_REPORT = "account_bulk_report"
    SPONSORED_PRODUCTS_SEARCH_TERM_REPORT = "sponsored_products_search_term_report"
    SPONSORED_PRODUCTS_TARGETING_REPORT = "sponsored_products_targeting_report"
    SPONSORED_PRODUCTS_CAMPAIGN_REPORT = "sponsored_products_campaign_report"
    BULK_SHEET = "bulk_sheet"
    UNKNOWN_REPORT = "unknown_report"


class UploadInitRequest(BaseModel):
    original_filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=255)
    file_size_bytes: Annotated[int, Field(gt=0)]
    source_type: str = Field(default=UploadSourceType.COMPETITOR_KEYWORD_RESEARCH.value, min_length=1, max_length=100)

    @field_validator("original_filename", "mime_type")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class UploadConfirmRequest(BaseModel):
    checksum: str | None = Field(default=None, max_length=256)


class UploadRecord(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID | None = None
    uploaded_by: str | None = None
    original_filename: str
    storage_path: str
    mime_type: str
    file_size_bytes: int
    status: UploadStatus
    source_type: UploadSourceType
    idempotency_key: str | None = None
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UploadInitResponse(BaseModel):
    upload_id: UUID
    storage_path: str
    upload_url: str
    upload_url_expires_at: datetime
    status: UploadStatus


class UploadConfirmResponse(BaseModel):
    upload_id: UUID
    status: UploadStatus
    job_id: UUID
