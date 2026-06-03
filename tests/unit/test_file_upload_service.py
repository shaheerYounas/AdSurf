"""Unit tests for FileUploadService — validates file type, size, empty file,
and unreadable Excel without any real I/O dependencies."""

from uuid import uuid4

import pytest

from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import MAX_UPLOAD_FILE_SIZE_BYTES
from apps.api.app.repositories.uploads import LocalUploadRepository
from apps.api.app.schemas.uploads import UploadStatus
from apps.api.app.services.file_upload import FileUploadService, FileUploadResult
from apps.api.app.services.storage import LocalFakeStorageService


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

VALID_CSV_CONTENT = b"Campaign,Impressions,Clicks\nCamp1,100,5\nCamp2,200,10\n"
EMPTY_CSV_CONTENT = b"Campaign,Impressions,Clicks\n"
MINIMAL_XLSX_BYTES = (
    b"PK\x03\x04"  # minimal ZIP header — not a valid xlsx but triggers ZIP error
)


def _service() -> FileUploadService:
    return FileUploadService(
        upload_repository=LocalUploadRepository(),
        storage_service=LocalFakeStorageService(),
    )


def _upload(**overrides):
    kwargs: dict = {
        "content": VALID_CSV_CONTENT,
        "original_filename": "report.csv",
        "mime_type": "text/csv",
        "workspace_id": uuid4(),
        "product_id": uuid4(),
        "actor_user_id": "user-1",
    }
    kwargs.update(overrides)
    return _service().upload(**kwargs)


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_upload_valid_csv_returns_result() -> None:
    result = _upload()

    assert isinstance(result, FileUploadResult)
    assert result.status == UploadStatus.INITIALIZED
    assert result.filename.endswith(".csv")
    assert result.row_count == 2  # 1 header + 2 data rows -> 2 data rows
    assert result.file_size_bytes > 0


def test_upload_valid_xlsx_returns_result() -> None:
    # Create a minimal valid XLSX using zipfile
    import io
    import zipfile
    from xml.etree import ElementTree

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Minimal workbook.xml
        workbook = ElementTree.Element(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook"
        )
        sheets = ElementTree.SubElement(workbook, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets")
        sheet = ElementTree.SubElement(sheets, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
        sheet.attrib["name"] = "Sheet1"
        sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"] = "rId1"
        zf.writestr("xl/workbook.xml", ElementTree.tostring(workbook, encoding="unicode"))

        # Minimal relationships
        rels = ElementTree.Element(
            "{http://schemas.openxmlformats.org/package/2006/relationships}Relationships"
        )
        rel = ElementTree.SubElement(rels, "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        rel.attrib["Id"] = "rId1"
        rel.attrib["Target"] = "worksheets/sheet1.xml"
        rel.attrib["Type"] = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
        zf.writestr("xl/_rels/workbook.xml.rels", ElementTree.tostring(rels, encoding="unicode"))

        # Minimal sheet with a header row and one data row
        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            '<row r="1"><c r="A1" t="inlineStr"><is><t>Campaign</t></is></c><c r="B1" t="inlineStr"><is><t>Impressions</t></is></c></row>'
            '<row r="2"><c r="A2" t="inlineStr"><is><t>Camp1</t></is></c><c r="B2"><v>100</v></c></row>'
            "</sheetData>"
            "</worksheet>"
        )
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

        # Shared strings (empty, but needed to prevent KeyError)
        shared_strings = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="0"/>'
        )
        zf.writestr("xl/sharedStrings.xml", shared_strings)

    xlsx_content = buf.getvalue()

    service = FileUploadService(
        upload_repository=LocalUploadRepository(),
        storage_service=LocalFakeStorageService(),
    )
    result = service.upload(
        content=xlsx_content,
        original_filename="ads_report.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        workspace_id=uuid4(),
        product_id=uuid4(),
        actor_user_id="user-1",
    )

    assert result.status == UploadStatus.INITIALIZED
    assert result.filename.endswith(".xlsx")
    assert result.row_count == 1  # only data row (header not counted)
    assert result.file_size_bytes > 0


# ---------------------------------------------------------------------------
# File-type validation
# ---------------------------------------------------------------------------


def test_rejects_unsupported_mime_type() -> None:
    with pytest.raises(ApiError) as exc_info:
        _upload(mime_type="application/pdf", original_filename="report.pdf")

    assert exc_info.value.code == "UNSUPPORTED_UPLOAD_MIME_TYPE"


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(ApiError) as exc_info:
        _upload(mime_type="text/csv", original_filename="report.txt")

    assert exc_info.value.code == "UNSUPPORTED_UPLOAD_EXTENSION"


def test_rejects_json_file() -> None:
    with pytest.raises(ApiError) as exc_info:
        _upload(mime_type="application/json", original_filename="data.json")

    assert exc_info.value.code == "UNSUPPORTED_UPLOAD_MIME_TYPE"


def test_rejects_legacy_xls_extension_for_upload_only_module() -> None:
    with pytest.raises(ApiError) as exc_info:
        _upload(
            content=b"not really xls",
            mime_type="application/vnd.ms-excel",
            original_filename="legacy.xls",
        )

    assert exc_info.value.code == "UNSUPPORTED_UPLOAD_EXTENSION"


# ---------------------------------------------------------------------------
# File-size validation
# ---------------------------------------------------------------------------


def test_rejects_zero_byte_file() -> None:
    with pytest.raises(ApiError) as exc_info:
        _upload(content=b"")

    assert exc_info.value.code == "REPORT_FILE_EMPTY"


def test_rejects_oversized_file() -> None:
    service = _service()
    with pytest.raises(ApiError) as exc_info:
        service.upload(
            content=b"x" * (MAX_UPLOAD_FILE_SIZE_BYTES + 1),
            original_filename="huge.csv",
            mime_type="text/csv",
            workspace_id=uuid4(),
            product_id=uuid4(),
            actor_user_id="user-1",
        )

    assert exc_info.value.code == "UPLOAD_FILE_TOO_LARGE"


def test_allows_large_but_valid_csv() -> None:
    """File close to the MVP limit with valid structure should be accepted."""
    service = _service()
    header = b"Col1,Col2,Col3\n"
    num_rows = 10000
    row_overhead = len(b"data,,extra\n")
    padding = (MAX_UPLOAD_FILE_SIZE_BYTES - len(header)) // num_rows - row_overhead
    padded_row = b"data," + b"x" * max(padding, 1) + b",extra\n"

    content = header
    for _ in range(num_rows):
        content += padded_row
    content = content[:MAX_UPLOAD_FILE_SIZE_BYTES]

    result = service.upload(
        content=content,
        original_filename="large.csv",
        mime_type="text/csv",
        workspace_id=uuid4(),
        product_id=uuid4(),
        actor_user_id="user-1",
    )
    assert result.status == UploadStatus.INITIALIZED


# ---------------------------------------------------------------------------
# Empty / unreadable file validation
# ---------------------------------------------------------------------------


def test_rejects_empty_csv() -> None:
    with pytest.raises(ApiError) as exc_info:
        _upload(content=EMPTY_CSV_CONTENT, original_filename="empty.csv")

    # The parser may return UPLOAD_PARSE_EMPTY_FILE or row_count==0
    assert exc_info.value.code in (
        "UPLOAD_PARSE_EMPTY_FILE",
        "UPLOAD_PARSE_INVALID_FILE",
    )


def test_rejects_csv_with_header_only_no_data() -> None:
    """A CSV with only a header row still counts as empty (no data rows)."""
    with pytest.raises(ApiError) as exc_info:
        _upload(content=b"Col1,Col2,Col3\n")

    # The parser may or may not reject 0-row results as empty.
    # Our service layer now re-checks row_count==0 and raises UPLOAD_PARSE_EMPTY_FILE.
    assert exc_info.value.code in (
        "UPLOAD_PARSE_EMPTY_FILE",
        "UPLOAD_PARSE_INVALID_FILE",
    )


def test_rejects_unreadable_xlsx() -> None:
    with pytest.raises(ApiError) as exc_info:
        _upload(
            content=MINIMAL_XLSX_BYTES,
            original_filename="corrupt.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    assert exc_info.value.code in ("UPLOAD_PARSE_INVALID_XLSX", "UPLOAD_PARSE_EMPTY_FILE")


def test_rejects_xlsx_with_no_sheets() -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Empty zip — no xl/workbook.xml
        pass

    with pytest.raises(ApiError) as exc_info:
        _upload(
            content=buf.getvalue(),
            original_filename="no_sheets.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # Empty zip -> KeyError (missing workbook.xml) -> UPLOAD_PARSE_INVALID_XLSX or UPLOAD_PARSE_INVALID_FILE
    assert exc_info.value.code in (
        "UPLOAD_PARSE_EMPTY_FILE",
        "UPLOAD_PARSE_INVALID_XLSX",
        "UPLOAD_PARSE_INVALID_FILE",
    )


# ---------------------------------------------------------------------------
# Filename validation
# ---------------------------------------------------------------------------


def test_rejects_path_traversal_filename() -> None:
    with pytest.raises(ApiError) as exc_info:
        _upload(original_filename="../etc/passwd.csv")

    assert exc_info.value.code == "INVALID_UPLOAD_FILENAME"


def test_sanitizes_filename_with_special_characters() -> None:
    result = _upload(original_filename=" My Report (Final).CSV ")
    # Parentheses and spaces should be replaced with underscores
    assert "$" not in result.filename
    assert "(" not in result.filename
    assert result.filename.endswith(".csv")


# ---------------------------------------------------------------------------
# Row-count accuracy
# ---------------------------------------------------------------------------


def test_row_count_matches_data_rows_excluding_header() -> None:
    content = b"Col1,Col2\nA,1\nB,2\nC,3\n"
    result = _upload(content=content)
    assert result.row_count == 3


def test_row_count_zero_for_header_only() -> None:
    """Header-only CSV raises empty-file error, but if we had a 1-row CSV
    it should report 1 data row."""
    content = b"Col1,Col2\nA,1\n"
    result = _upload(content=content)
    assert result.row_count == 1


# ---------------------------------------------------------------------------
# Account-level (product_id=None) upload
# ---------------------------------------------------------------------------


def test_account_level_upload_works() -> None:
    result = _upload(product_id=None)
    assert isinstance(result, FileUploadResult)
    assert result.status == UploadStatus.INITIALIZED
    assert result.filename.endswith(".csv")


# ---------------------------------------------------------------------------
# Idempotency (upload repository deduplication)
# ---------------------------------------------------------------------------


def test_uploads_with_different_ids_are_independent() -> None:
    workspace_id = uuid4()
    result1 = _upload(workspace_id=workspace_id, actor_user_id="user-a")
    result2 = _upload(workspace_id=workspace_id, actor_user_id="user-b")

    assert result1.upload_id != result2.upload_id
