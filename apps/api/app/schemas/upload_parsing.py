from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UploadParseStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ParsedUploadRow(BaseModel):
    id: UUID | None = None
    workspace_id: UUID | None = None
    product_id: UUID | None = None
    upload_id: UUID | None = None
    parse_run_id: UUID | None = None
    row_number: int
    row_data_json: dict
    row_hash: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UploadParseError(BaseModel):
    id: UUID | None = None
    workspace_id: UUID | None = None
    product_id: UUID | None = None
    upload_id: UUID | None = None
    parse_run_id: UUID | None = None
    row_number: int | None = None
    error_code: str
    error_message: str
    raw_value_json: dict | list | str | int | float | bool | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UploadParseRun(BaseModel):
    id: UUID
    workspace_id: UUID
    product_id: UUID
    upload_id: UUID
    job_id: UUID
    status: UploadParseStatus
    parser_version: str
    original_filename: str
    storage_path: str
    detected_file_type: str
    detected_sheet_names: list[str]
    selected_sheet_name: str | None = None
    total_rows: int = 0
    total_columns: int = 0
    parsed_rows_count: int = 0
    error_rows_count: int = 0
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ParsedUploadResult(BaseModel):
    detected_file_type: str
    detected_sheet_names: list[str] = []
    selected_sheet_name: str | None = None
    total_rows: int
    total_columns: int
    rows: list[ParsedUploadRow]
    errors: list[UploadParseError] = []
