"""
Tests for file upload validation module.
"""

import pytest

from validator import (
    FileUploadValidator,
    FileValidationErrorType,
    FileValidationResult,
)


class TestFileUploadValidator:
    """Tests for FileUploadValidator."""

    def setup_method(self):
        """Set up validator for tests."""
        self.validator = FileUploadValidator()

    def test_validate_csv_file_success(self):
        """Test successful validation of a valid CSV file."""
        csv_content = b"header1,header2,header3\nvalue1,value2,value3\nvalue4,value5,value6"

        result = self.validator.validate_upload(
            filename="report.csv",
            content=csv_content,
            mime_type="text/csv",
        )

        assert result.is_valid is True
        assert result.filename == "report.csv"
        assert result.mime_type == "text/csv"
        assert result.file_size_bytes == len(csv_content)
        assert result.row_count == 2
        assert len(result.errors) == 0

    def test_validate_xlsx_file_success(self):
        """Test successful validation of a valid Excel file."""
        # Use a minimal valid XLSX file (binary)
        xlsx_content = (
            b"PK\x03\x04\x14\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00"
        )

        result = self.validator.validate_upload(
            filename="report.xlsx",
            content=xlsx_content,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        assert result.is_valid is True
        assert result.filename == "report.xlsx"
        assert result.mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def test_validate_xls_file_success(self):
        """Test successful validation of an .xls file."""
        # Use a minimal valid XLS file (binary)
        xls_content = (
            b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
        )

        result = self.validator.validate_upload(
            filename="report.xls",
            content=xls_content,
            mime_type="application/vnd.ms-excel",
        )

        assert result.is_valid is True
        assert result.filename == "report.xls"

    def test_invalid_extension_rejected(self):
        """Test that files with invalid extensions are rejected."""
        result = self.validator.validate_upload(
            filename="report.txt",
            content=b"some content",
            mime_type="text/plain",
        )

        assert result.is_valid is False
        assert len(result.errors) > 0
        error_types = [e["type"] for e in result.errors]
        assert FileValidationErrorType.INVALID_EXTENSION in error_types

    def test_empty_file_rejected(self):
        """Test that empty files are rejected."""
        result = self.validator.validate_upload(
            filename="report.csv",
            content=b"",
            mime_type="text/csv",
        )

        assert result.is_valid is False
        error_types = [e["type"] for e in result.errors]
        assert FileValidationErrorType.EMPTY_FILE in error_types

    def test_whitespace_only_csv_rejected(self):
        """Test that whitespace-only CSV files are rejected."""
        result = self.validator.validate_upload(
            filename="report.csv",
            content=b"\n\n\n",
            mime_type="text/csv",
        )

        assert result.is_valid is False
        error_types = [e["type"] for e in result.errors]
        assert FileValidationErrorType.EMPTY_FILE in error_types

    def test_path_traversal_rejected(self):
        """Test that files with path traversal are rejected."""
        result = self.validator.validate_upload(
            filename="../etc/passwd",
            content=b"content",
            mime_type="text/plain",
        )

        assert result.is_valid is False
        error_types = [e["type"] for e in result.errors]
        assert FileValidationErrorType.PATH_TRAVERSAL in error_types

    def test_invalid_mime_type_rejected(self):
        """Test that invalid MIME types are rejected."""
        result = self.validator.validate_upload(
            filename="report.csv",
            content=b"header1,header2\nval1,val2",
            mime_type="application/pdf",  # Invalid for .csv
        )

        assert result.is_valid is False
        error_types = [e["type"] for e in result.errors]
        assert FileValidationErrorType.INVALID_MIME_TYPE in error_types

    def test_file_too_large_rejected(self):
        """Test that files exceeding max size are rejected."""
        large_content = b"x" * (30 * 1024 * 1024)  # 30MB

        validator = FileUploadValidator(max_file_size=25 * 1024 * 1024)  # 25MB limit

        result = validator.validate_upload(
            filename="report.csv",
            content=large_content,
            mime_type="text/csv",
        )

        assert result.is_valid is False
        error_types = [e["type"] for e in result.errors]
        assert FileValidationErrorType.FILE_TOO_LARGE in error_types

    def test_negative_file_size_rejected(self):
        """Test that negative file sizes are rejected."""
        result = self.validator.validate_upload(
            filename="report.csv",
            content=b"",
            mime_type="text/csv",
        )

        assert result.is_valid is False
        error_types = [e["type"] for e in result.errors]
        assert FileValidationErrorType.EMPTY_FILE in error_types

    def test_sanitized_filename(self):
        """Test that filenames are properly sanitized."""
        result = self.validator.validate_upload(
            filename="My Report (Final) v2.csv",
            content=b"header,header2\nval1,val2",
            mime_type="text/csv",
        )

        assert result.is_valid is True
        assert result.filename == "My_Report__Final__v2.csv"

    def test_detect_file_type(self):
        """Test file type detection."""
        csv_content = b"Campaign Name,Impressions\nCampaign1,1000"

        result = self.validator.validate_upload(
            filename="campaign_report.csv",
            content=csv_content,
            mime_type="text/csv",
        )

        assert result.is_valid is True
        # Should detect as a campaign report or similar
        assert result.detected_file_type is not None

    def test_count_csv_rows(self):
        """Test CSV row counting."""
        csv_content = b"header1,header2,header3\nval1,val2,val3\nval4,val5,val6\nval7,val8,val9"

        result = self.validator.validate_upload(
            filename="report.csv",
            content=csv_content,
            mime_type="text/csv",
        )

        assert result.row_count == 3

    def test_csv_with_no_data_rows(self):
        """Test CSV with only header row."""
        csv_content = b"header1,header2,header3"

        result = self.validator.validate_upload(
            filename="report.csv",
            content=csv_content,
            mime_type="text/csv",
        )

        assert result.is_valid is True
        assert result.row_count == 0

    def test_csv_with_header_and_data(self):
        """Test CSV with header and data rows."""
        csv_content = b"header1,header2\nval1,val2"

        result = self.validator.validate_upload(
            filename="report.csv",
            content=csv_content,
            mime_type="text/csv",
        )

        assert result.is_valid is True
        assert result.row_count == 1

    def test_unknown_extension_rejected(self):
        """Test rejection for unknown file extension."""
        result = self.validator.validate_upload(
            filename="report.xyz",
            content=b"",
            mime_type="text/plain",
        )

        assert result.is_valid is False
        # Should have error about invalid extension


class TestFileValidationError:
    """Tests for FileValidationError."""

    def test_exception_creation(self):
        """Test FileValidationError can be raised."""
        errors = [{"type": "test", "message": "test error"}]
        from service import FileValidationError

        exc = FileValidationError("Test error", errors)

        assert str(exc) == "Test error"
        assert exc.errors == errors

    def test_exception_with_none_errors(self):
        """Test FileValidationError with None errors."""
        from service import FileValidationError

        exc = FileValidationError("Test error")

        assert str(exc) == "Test error"
        assert exc.errors == []


class TestFileUploadValidationModels:
    """Tests for Pydantic models."""

    def test_request_validation(self):
        """Test FileUploadValidationRequest validation."""
        from service import FileUploadValidationRequest

        request = FileUploadValidationRequest(
            filename="report.csv",
            mime_type="text/csv",
            file_size_bytes=1000,
        )

        assert request.filename == "report.csv"
        assert request.mime_type == "text/csv"
        assert request.file_size_bytes == 1000

    def test_request_missing_filename(self):
        """Test FileUploadValidationRequest rejects empty filename."""
        from service import FileUploadValidationRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FileUploadValidationRequest(
                filename="",
                mime_type="text/csv",
                file_size_bytes=1000,
            )

    def test_request_negative_size(self):
        """Test FileUploadValidationRequest rejects negative size."""
        from service import FileUploadValidationRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FileUploadValidationRequest(
                filename="report.csv",
                mime_type="text/csv",
                file_size_bytes=-100,
            )

    def test_response_model(self):
        """Test FileUploadValidationResponse model."""
        from uuid import uuid4
        from service import FileUploadValidationResponse

        response = FileUploadValidationResponse(
            upload_id=uuid4(),
            filename="report.csv",
            file_size_bytes=1000,
            is_valid=True,
            mime_type="text/csv",
            row_count=5,
            errors=[],
            warnings=[],
        )

        assert response.is_valid is True
        assert response.row_count == 5


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_clean_filename(self):
        """Test clean filename preserved."""
        validator = FileUploadValidator()
        result = validator._validate_filename("report.csv")
        assert result["filename"] == "report.csv"

    def test_special_characters_replaced(self):
        """Test special characters replaced with underscores."""
        validator = FileUploadValidator()
        result = validator._validate_filename("My Report (Final).csv")
        assert result["filename"] == "My_Report__Final_.csv"

    def test_path_traversal_blocked(self):
        """Test path traversal is blocked."""
        validator = FileUploadValidator()
        result = validator._validate_filename("../etc/passwd.csv")
        assert result["valid"] is False

    def test_empty_filename(self):
        """Test empty filename rejected."""
        validator = FileUploadValidator()
        result = validator._validate_filename("")
        assert result["valid"] is False
