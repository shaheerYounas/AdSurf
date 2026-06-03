"""FileUploadService: lightweight upload module for Amazon Ads reports.

Accepts .xlsx and .csv files, validates them, stores metadata,
counts rows, and returns upload_id — without triggering analysis.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import (
    ACCEPTED_UPLOAD_EXTENSIONS,
    ACCEPTED_UPLOAD_MIME_TYPES,
    MAX_UPLOAD_FILE_SIZE_BYTES,
    build_upload_storage_path,
    sanitize_upload_filename,
)
from apps.api.app.schemas.uploads import UploadInitRequest, UploadRecord, UploadStatus, UploadSourceType
from apps.api.app.repositories.uploads import UploadRepository
from apps.api.app.services.storage import StorageService
from apps.api.app.services.upload_parser import UploadParser


@dataclass(frozen=True)
class FileUploadResult:
    """Result returned after a successful file upload and validation."""
    upload_id: UUID
    filename: str
    row_count: int | None
    status: UploadStatus
    file_size_bytes: int
    mime_type: str
    storage_path: str


class FileUploadService:
    """Validates, stores metadata, and counts rows for uploaded Amazon Ads reports.

    Intentionally does NOT trigger analysis, keyword scoring, campaign
    generation, or any downstream workflow.  This service is the “upload
    only” entry-point required by the MVP spec.
    """

    def __init__(
        self,
        *,
        upload_repository: UploadRepository,
        storage_service: StorageService,
    ) -> None:
        self._upload_repository = upload_repository
        self._storage_service = storage_service
        self._parser = UploadParser()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload(
        self,
        *,
        content: bytes,
        original_filename: str,
        mime_type: str,
        workspace_id: UUID,
        product_id: UUID | None,
        actor_user_id: str,
    ) -> FileUploadResult:
        """Validate, store, and return metadata for a single report file.

        Raises an ``ApiError`` for every failing validation so callers
        (API routes) can surface error codes like ``UNSUPPORTED_UPLOAD_MIME_TYPE``,
        ``UPLOAD_FILE_TOO_LARGE``, ``UPLOAD_PARSE_EMPTY_FILE``, or
        ``UPLOAD_PARSE_INVALID_XLSX``.
        """
        # 1. Preliminary validation via domain rules
        sanitized = self._validate_before_storage(
            original_filename=original_filename,
            mime_type=mime_type,
            file_size_bytes=len(content),
        )

        # 2. Deeper content validation + row-count extraction via UploadParser
        try:
            parsed = self._parser.parse(
                content=content,
                original_filename=sanitized,
                mime_type=mime_type,
            )
            row_count: int | None = parsed.total_rows
        except ApiError:
            raise
        except Exception as exc:
            raise ApiError(
                code="UPLOAD_PARSE_INVALID_FILE",
                message="Uploaded file could not be read as a valid spreadsheet.",
                status_code=400,
            ) from exc

        # 3. Reject files that parsed successfully but contain zero data rows
        if row_count is not None and row_count == 0:
            raise ApiError(
                code="UPLOAD_PARSE_EMPTY_FILE",
                message="Uploaded file has no data rows (header only).",
                status_code=400,
            )

        # 4. Persist upload metadata
        upload_id = uuid4()
        storage_path = build_upload_storage_path(
            workspace_id=workspace_id,
            product_id=product_id,
            upload_id=upload_id,
            sanitized_filename=sanitized,
        )

        source_type = (
            UploadSourceType.AMAZON_ADS_SP_SEARCH_TERM_REPORT.value
            if product_id is not None
            else UploadSourceType.ACCOUNT_BULK_REPORT.value
        )

        payload = UploadInitRequest(
            original_filename=sanitized,
            mime_type=mime_type,
            file_size_bytes=len(content),
            source_type=source_type,
        )

        upload_record = self._upload_repository.create_initialized(
            upload_id=upload_id,
            workspace_id=workspace_id,
            product_id=product_id,
            payload=payload,
            storage_path=storage_path,
            actor_user_id=actor_user_id,
            idempotency_key=str(uuid4()),
        )

        # 5. Store the raw file bytes
        self._storage_service.write_upload_object(
            storage_path=upload_record.storage_path,
            content=content,
        )

        return FileUploadResult(
            upload_id=upload_record.id,
            filename=upload_record.original_filename,
            row_count=row_count,
            status=upload_record.status,
            file_size_bytes=upload_record.file_size_bytes,
            mime_type=upload_record.mime_type,
            storage_path=upload_record.storage_path,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_before_storage(
        self,
        *,
        original_filename: str,
        mime_type: str,
        file_size_bytes: int,
    ) -> str:
        """Run lightweight pre-storage validations and return the sanitized filename."""
        # File-size checks
        if file_size_bytes <= 0:
            raise ApiError(
                code="REPORT_FILE_EMPTY",
                message="Uploaded file is empty (0 bytes).",
                status_code=400,
            )
        if file_size_bytes > MAX_UPLOAD_FILE_SIZE_BYTES:
            raise ApiError(
                code="UPLOAD_FILE_TOO_LARGE",
                message="Upload file exceeds the MVP size limit.",
                status_code=400,
                details={"max_file_size_bytes": MAX_UPLOAD_FILE_SIZE_BYTES},
            )

        # Type checks
        if mime_type not in ACCEPTED_UPLOAD_MIME_TYPES:
            raise ApiError(
                code="UNSUPPORTED_UPLOAD_MIME_TYPE",
                message="Upload MIME type is not supported.",
                status_code=400,
                details={"accepted_mime_types": sorted(ACCEPTED_UPLOAD_MIME_TYPES)},
            )

        sanitized = sanitize_upload_filename(original_filename)

        extension = _extension_for(sanitized)
        if extension not in ACCEPTED_UPLOAD_EXTENSIONS:
            raise ApiError(
                code="UNSUPPORTED_UPLOAD_EXTENSION",
                message="Upload file extension is not supported.",
                status_code=400,
                details={"accepted_extensions": sorted(ACCEPTED_UPLOAD_EXTENSIONS)},
            )

        return sanitized


def _extension_for(filename: str) -> str:
    dot_index = filename.rfind(".")
    return filename[dot_index:].lower() if dot_index >= 0 else ""