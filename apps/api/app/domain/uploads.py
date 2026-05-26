from pathlib import PurePath
import re
from uuid import UUID

from apps.api.app.core.errors import ApiError


MAX_UPLOAD_FILE_SIZE_BYTES = 25 * 1024 * 1024
MAX_PARSED_UPLOAD_ROWS = 50_000
MAX_PARSED_UPLOAD_COLUMNS = 250
SIGNED_UPLOAD_URL_EXPIRES_SECONDS = 15 * 60
PROCESS_UPLOAD_JOB_TYPE = "process_upload"
UPLOAD_PARSER_VERSION = "batch4-parser-v1"

ACCEPTED_UPLOAD_MIME_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
ACCEPTED_UPLOAD_EXTENSIONS = {".csv", ".xls", ".xlsx"}
ACCEPTED_UPLOAD_SOURCE_TYPES = {
    "competitor_keyword_research",
    "amazon_ads_sp_search_term_report",
}


def validate_upload_request(
    *,
    original_filename: str,
    mime_type: str,
    file_size_bytes: int,
    source_type: str,
) -> str:
    sanitized_filename = sanitize_upload_filename(original_filename)
    if mime_type not in ACCEPTED_UPLOAD_MIME_TYPES:
        raise ApiError(
            code="UNSUPPORTED_UPLOAD_MIME_TYPE",
            message="Upload MIME type is not supported.",
            status_code=400,
            details={"accepted_mime_types": sorted(ACCEPTED_UPLOAD_MIME_TYPES)},
        )
    if _extension_for(sanitized_filename) not in ACCEPTED_UPLOAD_EXTENSIONS:
        raise ApiError(
            code="UNSUPPORTED_UPLOAD_EXTENSION",
            message="Upload file extension is not supported.",
            status_code=400,
            details={"accepted_extensions": sorted(ACCEPTED_UPLOAD_EXTENSIONS)},
        )
    if file_size_bytes <= 0:
        raise ApiError(code="INVALID_UPLOAD_SIZE", message="Upload file size must be positive.", status_code=400)
    if file_size_bytes > MAX_UPLOAD_FILE_SIZE_BYTES:
        raise ApiError(
            code="UPLOAD_FILE_TOO_LARGE",
            message="Upload file exceeds the MVP size limit.",
            status_code=400,
            details={"max_file_size_bytes": MAX_UPLOAD_FILE_SIZE_BYTES},
        )
    if source_type not in ACCEPTED_UPLOAD_SOURCE_TYPES:
        raise ApiError(
            code="UNSUPPORTED_UPLOAD_SOURCE_TYPE",
            message="Upload source type is not supported.",
            status_code=400,
            details={"accepted_source_types": sorted(ACCEPTED_UPLOAD_SOURCE_TYPES)},
        )
    return sanitized_filename


def sanitize_upload_filename(original_filename: str) -> str:
    filename = original_filename.strip()
    if not filename:
        raise ApiError(code="INVALID_UPLOAD_FILENAME", message="Original filename is required.", status_code=400)
    if "/" in filename or "\\" in filename or PurePath(filename).name != filename:
        raise ApiError(code="INVALID_UPLOAD_FILENAME", message="Upload filename must not contain a path.", status_code=400)
    if ".." in filename:
        raise ApiError(code="INVALID_UPLOAD_FILENAME", message="Upload filename must not contain path traversal.", status_code=400)

    extension = _extension_for(filename)
    stem = filename[: -len(extension)] if extension else filename
    sanitized_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_-.")
    if not sanitized_stem:
        sanitized_stem = "upload"
    return f"{sanitized_stem}{extension.lower()}"


def build_upload_storage_path(
    *,
    workspace_id: UUID,
    product_id: UUID,
    upload_id: UUID,
    sanitized_filename: str,
) -> str:
    return f"/workspaces/{workspace_id}/products/{product_id}/uploads/{upload_id}/raw/{sanitized_filename}"


def _extension_for(filename: str) -> str:
    dot_index = filename.rfind(".")
    return filename[dot_index:].lower() if dot_index >= 0 else ""
