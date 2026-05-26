from uuid import uuid4

import pytest

from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import (
    MAX_UPLOAD_FILE_SIZE_BYTES,
    SIGNED_UPLOAD_URL_EXPIRES_SECONDS,
    build_upload_storage_path,
    sanitize_upload_filename,
    validate_upload_request,
)


def test_upload_constants_match_mvp_limits() -> None:
    assert MAX_UPLOAD_FILE_SIZE_BYTES == 25 * 1024 * 1024
    assert SIGNED_UPLOAD_URL_EXPIRES_SECONDS == 15 * 60


def test_filename_sanitization_preserves_extension() -> None:
    assert sanitize_upload_filename(" My Competitor Report (Final).XLSX ") == "My_Competitor_Report_Final.xlsx"


def test_filename_sanitization_rejects_path_traversal() -> None:
    with pytest.raises(ApiError) as error:
        sanitize_upload_filename("../keywords.csv")

    assert error.value.code == "INVALID_UPLOAD_FILENAME"


def test_upload_validation_rejects_bad_extension_after_sanitization() -> None:
    with pytest.raises(ApiError) as error:
        validate_upload_request(
            original_filename="keywords.json",
            mime_type="text/csv",
            file_size_bytes=100,
            source_type="competitor_keyword_research",
        )

    assert error.value.code == "UNSUPPORTED_UPLOAD_EXTENSION"


def test_storage_path_uses_server_generated_ids() -> None:
    workspace_id = uuid4()
    product_id = uuid4()
    upload_id = uuid4()

    assert build_upload_storage_path(
        workspace_id=workspace_id,
        product_id=product_id,
        upload_id=upload_id,
        sanitized_filename="keywords.csv",
    ) == f"/workspaces/{workspace_id}/products/{product_id}/uploads/{upload_id}/raw/keywords.csv"
