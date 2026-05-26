from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ColumnProfileStatus(StrEnum):
    GENERATED = "generated"
    FAILED = "failed"


class ColumnInferredDataType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    BOOLEAN = "boolean"
    UNKNOWN = "unknown"


class ColumnMappingStatus(StrEnum):
    DRAFT = "draft"
    VALID = "valid"
    INVALID = "invalid"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class ColumnMappingType(StrEnum):
    MANUAL = "manual"


class ColumnProfileColumn(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    upload_id: UUID
    parse_run_id: UUID
    column_profile_id: UUID
    original_column_name: str
    normalized_column_name: str
    column_index: int
    non_null_count: int
    sample_values_json: list
    inferred_data_type: ColumnInferredDataType
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ColumnProfile(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    upload_id: UUID
    parse_run_id: UUID
    status: ColumnProfileStatus
    total_columns: int
    total_rows_sampled: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ColumnProfileWithColumns(BaseModel):
    profile: ColumnProfile
    columns: list[ColumnProfileColumn]


class ManualMappingJson(BaseModel):
    search_term: str | None = None
    search_volume: str | None = None
    competitor_rank_columns: list[str] = Field(default_factory=list)


class ColumnMappingCreateRequest(BaseModel):
    column_profile_id: UUID
    mapping_json: ManualMappingJson


class ColumnMapping(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    upload_id: UUID
    parse_run_id: UUID
    column_profile_id: UUID
    status: ColumnMappingStatus
    mapping_version: int
    mapping_type: ColumnMappingType
    mapping_json: dict
    validation_errors_json: list[dict]
    created_by: UUID | None = None
    created_at: datetime
    approved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
