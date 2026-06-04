"""
File upload validation module for Amazon Ads reports.

This module handles validation of uploaded files before they are processed.
Validation includes: file type, file size, empty file, and unreadable Excel checks.

All validations follow the safety rule: no processing occurs without validation.
"""

import io
import logging
import mimetypes
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional
from uuid import UUID, uuid4

from PIL import Image
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class FileValidationErrorType(StrEnum):
    """Types of file validation errors."""
    INVALID_EXTENSION = "invalid_extension"
    INVALID_MIME_TYPE = "invalid_mime_type"
    FILE_TOO_LARGE = "file_too_large"
    EMPTY_FILE = "empty_file"
    UNREADABLE_EXCEL = "unreadable_excel"
    PATH_TRAVERSAL = "path_traversal"
    INVALID_FILENAME = "invalid_filename"


@dataclass
class FileValidationResult:
    """Result of file validation."""
    upload_id: UUID
    filename: str
    file_size_bytes: int
    is_valid: bool
    mime_type: str
    row_count: Optional[int] = None
    errors: list[dict] = None
    warnings: list[dict] = None
    detection_confidence: Optional[float] = None
    detected_file_type: Optional[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class FileUploadValidator:
    """
    Validates uploaded files before processing.

    Follows the safety rule: no file processing occurs without validation.
    Validates file type, size, empty files, and Excel readability.
    """

    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25MB
    MAX_PIXELS = 256 * 256  # For image-based checks

    # Accepted file extensions
    ACCEPTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

    # Accepted MIME types
    ACCEPTED_MIME_TYPES = {
        "text/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }

    # Known Amazon Ads report prefixes for detection
    AMAZON_REPORT_PREFIXES = {
        "sponsored_products_search_term_report": ["Sponsored Products", "Search"],
        "sponsored_products_campaign_report": ["Sponsored Products", "Campaign"],
        "sponsored_products_targeting_report": ["Sponsored Products", "Targeting"],
    }

    def __init__(
        self,
        *,
        max_file_size: int | None = None,
        validate_excel: bool = True,
    ):
        self.max_file_size = max_file_size or self.MAX_FILE_SIZE_BYTES
        self.validate_excel = validate_excel

    def validate_upload(
        self,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None = None,
        workspace_id: UUID | None = None,
        upload_id: UUID | None = None,
    ) -> FileValidationResult:
        """
        Validate a file upload request.

        Returns FileValidationResult with:
        - upload_id: UUID for the upload
        - filename: validated/sanitized filename
        - file_size_bytes: file size
        - is_valid: boolean indicating if validation passed
        - mime_type: validated MIME type
        - row_count: estimated row count (for CSV)
        - errors: list of error details
        - warnings: list of warning details
        """
        errors: list[dict] = []
        warnings: list[dict] = []
        upload_id = upload_id or uuid4()

        # Step 1: Validate filename
        filename_result = self._validate_filename(filename)
        if not filename_result.get("valid", False):
            errors.extend(filename_result.get("errors", []))
        else:
            filename = filename_result["filename"]

        # Step 2: Validate MIME type
        mime_result = self._validate_mime_type(mime_type or "", filename)
        if not mime_result.get("valid", False):
            errors.extend(mime_result.get("errors", []))
        else:
            mime_type = mime_result.get("mime_type", mime_type)

        # Step 3: Validate file size
        size_result = self._validate_file_size(len(content))
        if not size_result.get("valid", False):
            errors.extend(size_result.get("errors", []))

        # Step 4: Check for empty file
        empty_result = self._check_empty_file(content, filename)
        if not empty_result.get("valid", False):
            errors.extend(empty_result.get("errors", []))

        # Step 5: Validate Excel files are readable
        excel_result = None
        if mime_type in {"application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}:
            excel_result = self._validate_excel_readability(content, filename)
            if excel_result and not excel_result.get("valid", False):
                errors.extend(excel_result.get("errors", []))

        # Step 6: Detect file type (for non-error cases)
        detected_type = None
        detection_confidence = None
        if not errors:
            detect_result = self._detect_file_type(content, filename)
            detected_type = detect_result.get("detected_type")
            detection_confidence = detect_result.get("confidence")
            warnings.extend(detect_result.get("warnings", []))

        # Step 7: Count rows for CSV files (for row_count output)
        row_count = None
        if mime_type == "text/csv" and not errors:
            row_count = self._count_csv_rows(content)

        is_valid = len(errors) == 0

        return FileValidationResult(
            upload_id=upload_id,
            filename=filename,
            file_size_bytes=len(content),
            is_valid=is_valid,
            mime_type=mime_type,
            row_count=row_count,
            errors=errors,
            warnings=warnings,
            detection_confidence=detection_confidence,
            detected_file_type=detected_type,
        )

    def _validate_filename(self, filename: str) -> dict:
        """Validate filename is safe and acceptable."""
        errors = []

        if not filename or not filename.strip():
            return {"valid": False, "errors": [{"type": FileValidationErrorType.INVALID_FILENAME, "message": "Filename is required"}]}

        filename = filename.strip()

        # Check for path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            return {"valid": False, "errors": [{"type": FileValidationErrorType.PATH_TRAVERSAL, "message": "Filename must not contain path separators"}]}

        # Check for extension
        ext = self._get_extension(filename)
        if ext not in self.ACCEPTED_EXTENSIONS:
            return {
                "valid": False,
                "errors": [{
                    "type": FileValidationErrorType.INVALID_EXTENSION,
                    "message": f"File extension not supported. Allowed: {', '.join(sorted(self.ACCEPTED_EXTENSIONS))}",
                    "details": {"received": ext, "allowed": list(self.ACCEPTED_EXTENSIONS)}
                }]
            }

        # Sanitize filename
        stem = filename.rsplit(".", 1)[0]
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem)
        if not stem or len(stem) > 200:
            stem = "upload"
        sanitized = f"{stem}{ext.lower()}"

        return {"valid": True, "filename": sanitized}

    def _check_empty_file(self, content: bytes, filename: str) -> dict:
        """Check if file is effectively empty."""
        errors = []

        # Check for completely empty file
        if len(content) == 0:
            return {
                "valid": False,
                "errors": [{
                    "type": FileValidationErrorType.EMPTY_FILE,
                    "message": "File is empty",
                    "details": {"filename": filename}
                }]
            }

        # Check for whitespace-only CSV
        if filename.endswith(".csv"):
            stripped = content.strip()
            if not stripped or stripped == b"\n" * stripped.count(b"\n"):
                return {
                    "valid": False,
                    "errors": [{
                        "type": FileValidationErrorType.EMPTY_FILE,
                        "message": "File contains no data",
                        "details": {"filename": filename}
                    }]
                }

        # Check for whitespace-only Excel (detect by looking for minimal structured content)
        if filename.endswith((".xls", ".xlsx")):
            # Basic check - if file is very small and has no recognizable Excel header
            if len(content) < 512:
                return {
                    "valid": False,
                    "errors": [{
                        "type": FileValidationErrorType.EMPTY_FILE,
                        "message": "File appears to be empty or too small to be valid",
                        "details": {"filename": filename, "size_bytes": len(content)}
                    }]
                }

        return {"valid": True}

    def _validate_mime_type(self, mime_type: str, filename: str) -> dict:
        """Validate MIME type matches expected for file extension."""
        errors = []
        ext = self._get_extension(filename)

        if not mime_type:
            # Infer from extension
            inferred, _ = mimetypes.guess_type(filename)
            mime_type = inferred or ""

        if mime_type not in self.ACCEPTED_MIME_TYPES:
            return {
                "valid": False,
                "errors": [{
                    "type": FileValidationErrorType.INVALID_MIME_TYPE,
                    "message": f"MIME type not supported. Allowed: {', '.join(sorted(self.ACCEPTED_MIME_TYPES))}",
                    "details": {"received": mime_type, "allowed": list(self.ACCEPTED_MIME_TYPES), "filename": filename}
                }]
            }

        # Cross-check extension with MIME type
        expected_for_ext = {
            ".csv": "text/csv",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

        if ext in expected_for_ext and mime_type != expected_for_ext[ext]:
            warnings = [{
                "type": "mime_type_mismatch",
                "message": f"MIME type ({mime_type}) does not match expected for extension {ext} ({expected_for_ext[ext]}). File may be malformed.",
            }]
            return {"valid": True, "mime_type": mime_type, "warnings": warnings}

        return {"valid": True, "mime_type": mime_type}

    def _validate_file_size(self, size_bytes: int) -> dict:
        """Validate file size is within limits."""
        if size_bytes <= 0:
            return {
                "valid": False,
                "errors": [{
                    "type": FileValidationErrorType.EMPTY_FILE,
                    "message": "File size must be positive",
                    "details": {"size_bytes": size_bytes}
                }]
            }

        if size_bytes > self.max_file_size:
            return {
                "valid": False,
                "errors": [{
                    "type": FileValidationErrorType.FILE_TOO_LARGE,
                    "message": f"File exceeds maximum size limit",
                    "details": {"size_bytes": size_bytes, "max_bytes": self.max_file_size}
                }]
            }

        return {"valid": True}

    def _check_empty_file(self, content: bytes, filename: str) -> dict:
        """Check if file is effectively empty."""
        errors = []

        # Check for completely empty file
        if len(content) == 0:
            return {
                "valid": False,
                "errors": [{
                    "type": FileValidationErrorType.EMPTY_FILE,
                    "message": "File is empty",
                    "details": {"filename": filename}
                }]
            }

        # Check for whitespace-only CSV
        if filename.endswith(".csv"):
            stripped = content.strip()
            if not stripped or stripped == b"\n" * stripped.count(b"\n"):
                return {
                    "valid": False,
                    "errors": [{
                        "type": FileValidationErrorType.EMPTY_FILE,
                        "message": "File contains no data",
                        "details": {"filename": filename}
                    }]
                }

        # Check for whitespace-only Excel (detect by looking for minimal structured content)
        if filename.endswith((".xls", ".xlsx")):
            # Basic check - if file is very small and has no recognizable Excel header
            if len(content) < 512:
                return {
                    "valid": False,
                    "errors": [{
                        "type": FileValidationErrorType.EMPTY_FILE,
                        "message": "File appears to be empty or too small to be valid",
                        "details": {"filename": filename, "size_bytes": len(content)}
                    }]
                }

        return {"valid": True}

    def _validate_excel_readability(self, content: bytes, filename: str) -> dict:
        """
        Validate that an Excel file is actually readable.

        This ensures the file isn't corrupted and can be parsed.
        """
        errors = []

        # Try to open as Excel using different libraries
        try:
            import openpyxl
            try:
                from io import BytesIO
                workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
                workbook.close()
                return {"valid": True}
            except Exception as e:
                errors.append({
                    "type": FileValidationErrorType.UNREADABLE_EXCEL,
                    "message": "Excel file could not be read",
                    "details": {"filename": filename, "error": str(e), "library": "openpyxl"}
                })
        except ImportError:
            pass

        try:
            import xlrd
            try:
                from io import BytesIO
                workbook = xlrd.open_workbook(file_contents=content)
                # Try to read a sheet
                sheet = workbook.sheet_by_index(0)
                if sheet.nrows == 0:
                    return {
                        "valid": False,
                        "errors": [{
                            "type": FileValidationErrorType.EMPTY_FILE,
                            "message": "Excel file contains no rows",
                            "details": {"filename": filename}
                        }]
                    }
                return {"valid": True}
            except Exception as e:
                errors.append({
                    "type": FileValidationErrorType.UNREADABLE_EXCEL,
                    "message": "Excel file could not be read",
                    "details": {"filename": filename, "error": str(e), "library": "xlrd"}
                })
        except ImportError:
            pass

        # If neither library is available, return warning but allow processing
        if not errors:
            return {"valid": True, "warnings": [{"type": "no_excel_parser", "message": "No Excel parser libraries available, skipping validation"}]}

        return {"valid": False, "errors": errors}

    def _detect_file_type(self, content: bytes, filename: str) -> dict:
        """Detect the type of Amazon Ads report in the file."""
        detected_type = None
        confidence = 0.0
        warnings = []

        # Check for Amazon report patterns in first few lines
        if filename.endswith(".csv"):
            try:
                text = content.decode("utf-8", errors="replace")
                lines = text.split("\n")[:10]
                text_sample = " ".join(lines)

                for report_type, keywords in self.AMAZON_REPORT_PREFIXES.items():
                    matches = sum(1 for kw in keywords if kw.lower() in text_sample.lower())
                    if matches >= 2:
                        detected_type = report_type
                        confidence = matches / len(keywords)
                        break
            except Exception:
                pass

        # Check for common report headers
        if not detected_type:
            sample = content[:1000].decode("utf-8", errors="replace").lower()
            headers_to_type = {
                "search term": "sponsored_products_search_term_report",
                "campaign name": "sponsored_products_campaign_report",
                "targeting": "sponsored_products_targeting_report",
                "asin": "sponsored_products_campaign_report",
                "keyword": "sponsored_products_search_term_report",
            }

            for header, report_type in headers_to_type.items():
                if header in sample:
                    detected_type = report_type
                    confidence = 0.5
                    break

        if not detected_type:
            warnings.append({
                "type": "unknown_report_type",
                "message": "Report type could not be automatically detected",
            })
            detected_type = "unknown_report"
            confidence = 0.0

        return {
            "detected_type": detected_type,
            "confidence": confidence,
            "warnings": warnings,
        }

    def _count_csv_rows(self, content: bytes) -> int:
        """Count rows in a CSV file."""
        try:
            text = content.decode("utf-8", errors="replace")
            lines = text.strip().split("\n")
            # Subtract 1 for header row if file has content
            return max(0, len(lines) - 1) if len(lines) > 1 else 0
        except Exception:
            return 0

    def _get_extension(self, filename: str) -> str:
        """Get file extension in lowercase."""
        if "." in filename:
            ext = filename.rsplit(".", 1)[-1]
            return f".{ext.lower()}"
        return ""


# Pydantic models for API request validation
class FileUploadValidationRequest(BaseModel):
    """Request model for file upload validation."""
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str | None = Field(default=None, max_length=255)
    file_size_bytes: int = Field(gt=0)
    source_type: str | None = Field(default=None, max_length=100)

    @field_validator("filename")
    @classmethod
    def strip_filename(cls, v: str) -> str:
        return v.strip()


class FileUploadValidationResponse(BaseModel):
    """Response model for file upload validation."""
    upload_id: UUID
    filename: str
    file_size_bytes: int
    is_valid: bool
    mime_type: str
    row_count: int | None = None
    errors: list[dict] = []
    warnings: list[dict] = []
    detection_confidence: float | None = None
    detected_file_type: str | None = None


# Exception for validation failures
class FileValidationError(Exception):
    """Raised when file validation fails."""
    def __init__(self, message: str, errors: list[dict] | None = None):
        super().__init__(message)
        self.errors = errors or []
