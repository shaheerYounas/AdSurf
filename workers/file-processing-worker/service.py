"""
File upload service for Amazon Ads reports.

This module provides the upload service that uses FileUploadValidator
to validate files and store their metadata.

Follows the safety rule: no file is stored or processed without validation.
"""

import logging
import mimetypes
from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel

from validator import FileUploadValidator, FileValidationResult

logger = logging.getLogger(__name__)


class StorageResult(BaseModel):
    """Result of storing a file in storage."""
    storage_path: str
    etag: Optional[str] = None


@dataclass
class UploadMetadata:
    """Metadata for an uploaded file."""
    upload_id: UUID
    original_filename: str
    sanitized_filename: str
    file_size_bytes: int
    mime_type: str
    status: str
    row_count: Optional[int]
    detected_file_type: Optional[str]
    detection_confidence: Optional[float]
    errors: list[dict]
    warnings: list[dict]


class FileUploadService:
    """
    Service for handling file uploads with validation.

    Ensures all uploads go through FileUploadValidator before any storage.
    Stores metadata in a repository (to be implemented).
    """

    def __init__(
        self,
        *,
        validator: FileUploadValidator | None = None,
    ):
        self.validator = validator or FileUploadValidator()

    def upload(
        self,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None = None,
        workspace_id: UUID | None = None,
        product_id: UUID | None = None,
    ) -> tuple[UploadMetadata, Optional[StorageResult]]:
        """
        Handle a file upload with validation.

        Returns:
            - UploadMetadata: Metadata about the uploaded file
            - StorageResult: Result of storing the file (if valid)

        Safety rule applied: No storage occurs if validation fails.
        """
        # Step 1: Validate the file
        validation_result = self.validator.validate_upload(
            filename=filename,
            content=content,
            mime_type=mime_type,
            workspace_id=workspace_id,
        )

        # Step 2: Handle validation result
        if not validation_result.is_valid:
            logger.warning(
                "Upload validation failed",
                extra={
                    "upload_id": str(validation_result.upload_id),
                    "filename": filename,
                    "errors": validation_result.errors,
                    "warnings": validation_result.warnings,
                }
            )
            return self._create_failed_metadata(validation_result), None

        # Step 3: If valid, store file metadata (no actual storage yet)
        storage_result = self._create_storage_path(
            upload_id=validation_result.upload_id,
            filename=validation_result.filename,
            workspace_id=workspace_id,
            product_id=product_id,
        )

        logger.info(
            "Upload validated successfully",
            extra={
                "upload_id": str(validation_result.upload_id),
                "filename": validation_result.filename,
                "file_size_bytes": validation_result.file_size_bytes,
                "mime_type": validation_result.mime_type,
            }
        )

        return self._create_success_metadata(validation_result, storage_result), storage_result

    def validate_only(
        self,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None = None,
        workspace_id: UUID | None = None,
    ) -> FileValidationResult:
        """
        Validate a file without storing anything.

        Returns FileValidationResult with errors/warnings but doesn't store.
        Used for pre-flight validation before actual upload.
        """
        return self.validator.validate_upload(
            filename=filename,
            content=content,
            mime_type=mime_type,
            workspace_id=workspace_id,
        )

    def _create_storage_path(
        self,
        *,
        upload_id: UUID,
        filename: str,
        workspace_id: UUID | None = None,
        product_id: UUID | None = None,
    ) -> StorageResult:
        """Create the storage path for the uploaded file."""
        if product_id:
            storage_path = f"workspaces/{workspace_id}/products/{product_id}/uploads/{upload_id}/raw/{filename}"
        elif workspace_id:
            storage_path = f"workspaces/{workspace_id}/uploads/{upload_id}/raw/{filename}"
        else:
            storage_path = f"uploads/{upload_id}/raw/{filename}"

        # Generate a simple ETag (in production, this would be an actual ETag)
        etag = f'"{upload_id.hex}"'

        return StorageResult(storage_path=storage_path, etag=etag)

    def _create_failed_metadata(
        self,
        result: FileValidationResult,
    ) -> UploadMetadata:
        """Create metadata for a failed upload."""
        return UploadMetadata(
            upload_id=result.upload_id,
            original_filename=result.filename,
            sanitized_filename=result.filename,
            file_size_bytes=result.file_size_bytes,
            mime_type=result.mime_type,
            status="validation_failed",
            row_count=None,
            detected_file_type=None,
            detection_confidence=None,
            errors=result.errors,
            warnings=result.warnings,
        )

    def _create_success_metadata(
        self,
        result: FileValidationResult,
        storage: StorageResult,
    ) -> UploadMetadata:
        """Create metadata for a successful upload."""
        return UploadMetadata(
            upload_id=result.upload_id,
            original_filename=result.filename,
            sanitized_filename=result.filename,
            file_size_bytes=result.file_size_bytes,
            mime_type=result.mime_type,
            status="validated",
            row_count=result.row_count,
            detected_file_type=result.detected_file_type,
            detection_confidence=result.detection_confidence,
            errors=[],
            warnings=result.warnings,
        )


# Helper functions for common use cases
def get_mime_type_from_filename(filename: str) -> str:
    """Get MIME type for a filename based on extension."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def is_excel_file(filename: str) -> bool:
    """Check if filename appears to be an Excel file."""
    return filename.lower().endswith((".xls", ".xlsx"))


def is_csv_file(filename: str) -> bool:
    """Check if filename appears to be a CSV file."""
    return filename.lower().endswith(".csv")


class HealthCheckResult(BaseModel):
    """Health check result for the upload service."""
    status: str
    version: str
    validator_ready: bool


def health_check() -> HealthCheckResult:
    """Perform health check on the upload service."""
    try:
        validator = FileUploadValidator()
        # Test with a known good file
        test_csv = b"header1,header2\nvalue1,value2\nvalue3,value4"
        result = validator.validate_upload(
            filename="test.csv",
            content=test_csv,
            mime_type="text/csv",
        )
        return HealthCheckResult(
            status="healthy",
            version="1.0.0",
            validator_ready=result.is_valid,
        )
    except Exception as e:
        return HealthCheckResult(
            status="unhealthy",
            version="1.0.0",
            validator_ready=False,
        )
