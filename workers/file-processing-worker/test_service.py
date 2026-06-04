"""Tests for file upload service."""

from datetime import datetime
from uuid import uuid4

from validator import FileUploadValidator, FileValidationResult
from service import FileUploadService, StorageResult, UploadMetadata, FileValidationError, health_check, get_mime_type_from_filename, is_excel_file, is_csv_file


class TestFileUploadService:
    """Tests for FileUploadService."""

    def setup_method(self):
        """Set up service for tests."""
        self.service = FileUploadService()

    @pytest.fixture
    def service(self):
        """Return a fresh service instance for each test."""
        return FileUploadService()

    def test_upload_valid_csv(self, service):
        """Test successful CSV upload."""
        csv_content = b"header1,header2,header3\nval1,val2,val3\nval4,val5,val6"

        upload_id = uuid4()
        metadata, storage = self.service.upload(
            filename="report.csv",
            content=csv_content,
            mime_type="text/csv",
            workspace_id=uuid4(),
        )

        assert metadata.upload_id == upload_id
        assert metadata.is_valid is True
        assert metadata.status == "validated"
        assert metadata.mime_type == "text/csv"
        assert metadata.row_count == 2
        assert metadata.errors == []
        assert storage is not None
        assert storage.storage_path is not None

    def test_upload_invalid_extension(self):
        """Test upload with invalid extension fails."""
        metadata, storage = self.service.upload(
            filename="report.txt",
            content=b"content",
            mime_type="text/plain",
        )

        assert metadata.status == "validation_failed"
        assert metadata.errors != []
        assert storage is None

    def test_upload_empty_file(self):
        """Test upload with empty file fails."""
        metadata, storage = self.service.upload(
            filename="report.csv",
            content=b"",
            mime_type="text/csv",
        )

        assert metadata.status == "validation_failed"
        assert metadata.errors != []
        assert storage is None

    def test_validate_only(self):
        """Test validate_only returns result without storage."""
        csv_content = b"header1,header2\nval1,val2"

        result = self.service.validate_only(
            filename="report.csv",
            content=csv_content,
            mime_type="text/csv",
        )

        assert result.is_valid is True
        assert result.filename == "report.csv"
        assert result.row_count == 1


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_mime_type_from_filename_csv(self):
        """Test MIME type inference for CSV."""
        from service import get_mime_type_from_filename
        mime = get_mime_type_from_filename("data.csv")
        assert mime == "text/csv"

    def test_get_mime_type_from_filename_xlsx(self):
        """Test MIME type inference for XLSX."""
        from service import get_mime_type_from_filename
        mime = get_mime_type_from_filename("data.xlsx")
        assert mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def test_get_mime_type_from_filename_unknown(self):
        """Test MIME type inference for unknown file."""
        from service import get_mime_type_from_filename
        mime = get_mime_type_from_filename("data.xyz")
        assert mime is None

    def test_is_excel_file(self):
        """Test Excel file detection."""
        from service import is_excel_file
        assert is_excel_file("report.xlsx") is True
        assert is_excel_file("report.xls") is True
        assert is_excel_file("report.csv") is False

    def test_is_csv_file(self):
        """Test CSV file detection."""
        from service import is_csv_file
        assert is_csv_file("report.csv") is True
        assert is_csv_file("report.xlsx") is False

    def test_health_check(self):
        """Test health check returns healthy state."""
        from service import health_check
        result = health_check()

        assert result.status == "healthy"
        assert result.version == "1.0.0"
        assert result.validator_ready is True


class TestStoragePathCreation:
    """Tests for storage path creation."""

    def test_storage_path_with_workspace_and_product(self, service):
        """Test storage path with workspace and product."""
        workspace_id = uuid4()
        product_id = uuid4()
        upload_id = uuid4()

        storage = service._create_storage_path(
            upload_id=upload_id,
            filename="report.csv",
            workspace_id=workspace_id,
            product_id=product_id,
        )

        expected = f"workspaces/{workspace_id}/products/{product_id}/uploads/{upload_id}/raw/report.csv"
        assert storage.storage_path == expected
        assert storage.etag is not None

    def test_storage_path_with_workspace_only(self, service):
        """Test storage path with workspace only."""
        workspace_id = uuid4()
        upload_id = uuid4()

        storage = service._create_storage_path(
            upload_id=upload_id,
            filename="report.csv",
            workspace_id=workspace_id,
        )

        expected = f"workspaces/{workspace_id}/uploads/{upload_id}/raw/report.csv"
        assert storage.storage_path == expected

    def test_storage_path_without_workspace(self, service):
        """Test storage path without workspace."""
        upload_id = uuid4()

        storage = service._create_storage_path(
            upload_id=upload_id,
            filename="report.csv",
        )

        expected = f"uploads/{upload_id}/raw/report.csv"
        assert storage.storage_path == expected


class TestMetadataCreation:
    """Tests for metadata creation."""

    def test_success_metadata(self, service):
        """Test creation of success metadata."""
        result = FileValidationResult(
            upload_id=uuid4(),
            filename="report.csv",
            file_size_bytes=1000,
            is_valid=True,
            mime_type="text/csv",
            row_count=5,
            detected_file_type="sponsored_products_search_term_report",
            detection_confidence=0.9,
            errors=[],
            warnings=[],
        )

        storage = StorageResult(
            storage_path="workspaces/test/uploads/test/raw/report.csv",
            etag="\"test\"",
        )

        metadata = service._create_success_metadata(result, storage)

        assert metadata.status == "validated"
        assert metadata.row_count == 5
        assert metadata.detected_file_type == "sponsored_products_search_term_report"
        assert metadata.detection_confidence == 0.9
        assert metadata.errors == []

    def test_failed_metadata(self, service):
        """Test creation of failed metadata."""
        result = FileValidationResult(
            upload_id=uuid4(),
            filename="report.txt",
            file_size_bytes=0,
            is_valid=False,
            mime_type="text/plain",
            errors=[{"type": "invalid_extension", "message": "Extension not allowed"}],
            warnings=[],
        )

        metadata = service._create_failed_metadata(result)

        assert metadata.status == "validation_failed"
        assert metadata.errors != []


class TestServiceIntegration:
    """Integration tests for service components."""

    def test_full_upload_flow(self):
        """Test complete upload flow end-to-end."""
        csv_content = b"header1,header2,header3\nval1,val2,val3\nval4,val5,val6\nval7,val8,val9"

        workspace_id = uuid4()
        upload_id = uuid4()

        metadata, storage = self.service.upload(
            filename="sponsored_products_search_term_report.csv",
            content=csv_content,
            mime_type="text/csv",
            workspace_id=workspace_id,
            upload_id=upload_id,
        )

        # Verify all components
        assert metadata.upload_id == upload_id
        assert metadata.sanitized_filename == "sponsored_products_search_term_report.csv"
        assert metadata.file_size_bytes == len(csv_content)
        assert metadata.mime_type == "text/csv"
        assert metadata.status == "validated"
        assert metadata.row_count == 3
        assert metadata.detected_file_type is not None
        assert metadata.detection_confidence is not None
        assert metadata.errors == []
        assert storage is not None
        assert storage.storage_path is not None
        assert workspace_id.hex in storage.storage_path

    def test_invalid_upload_flow(self):
        """Test invalid upload flow end-to-end."""
        metadata, storage = self.service.upload(
            filename="../etc/passwd.csv",
            content=b"content",
            mime_type="text/csv",
        )

        assert metadata.status == "validation_failed"
        assert storage is None
        assert any(e["type"] == "path_traversal" for e in metadata.errors)

    def test_large_file_rejection(self):
        """Test large file rejection in service."""
        # Create a large content that exceeds 25MB
        large_content = b"x" * (30 * 1024 * 1024)  # 30MB

        service = FileUploadService()
        metadata, storage = service.upload(
            filename="large_report.csv",
            content=large_content,
            mime_type="text/csv",
        )

        assert metadata.status == "validation_failed"
        assert storage is None
        assert any(e["type"] == "file_too_large" for e in metadata.errors)


class TestFileValidationError:
    """Tests for FileValidationError."""

    def test_exception_creation(self):
        """Test FileValidationError can be raised."""
        errors = [{"type": "test", "message": "test error"}]
        exc = FileValidationError("Test error", errors)

        assert str(exc) == "Test error"
        assert exc.errors == errors

    def test_exception_with_none_errors(self):
        """Test FileValidationError with None errors."""
        exc = FileValidationError("Test error")

        assert str(exc) == "Test error"
        assert exc.errors == []
