"""Integration tests for the upload-only file-upload endpoint.

POST /v1/workspaces/{workspace_id}/file-uploads
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.main import app


client = TestClient(app)


def auth_headers(workspace_id: str, role: str = "owner", user_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "x-user-id": user_id,
        "x-test-workspaces": f"{workspace_id}:{role}",
    }


# ---------------------------------------------------------------------------
# Happy-path multipart upload
# ---------------------------------------------------------------------------


def test_multipart_file_upload_returns_upload_id_and_row_count() -> None:
    workspace_id = str(uuid4())
    content = b"Campaign,Impressions,Clicks\nCamp1,100,5\nCamp2,200,10\n"

    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id, role="analyst"),
        files={"file": ("report.csv", content, "text/csv")},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["upload_id"]
    assert data["filename"] == "report.csv"
    assert data["row_count"] == 2
    assert data["status"] == "initialized"


def test_multipart_file_upload_xlsx_succeeds() -> None:
    """Upload a minimal valid XLSX file and verify it succeeds."""
    import io
    import zipfile
    from xml.etree import ElementTree

    workspace_id = str(uuid4())

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        workbook = ElementTree.Element(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook"
        )
        sheets = ElementTree.SubElement(workbook, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets")
        sheet = ElementTree.SubElement(sheets, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
        sheet.attrib["name"] = "Sheet1"
        sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"] = "rId1"
        zf.writestr("xl/workbook.xml", ElementTree.tostring(workbook, encoding="unicode"))

        rels = ElementTree.Element(
            "{http://schemas.openxmlformats.org/package/2006/relationships}Relationships"
        )
        rel = ElementTree.SubElement(rels, "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        rel.attrib["Id"] = "rId1"
        rel.attrib["Target"] = "worksheets/sheet1.xml"
        rel.attrib["Type"] = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
        zf.writestr("xl/_rels/workbook.xml.rels", ElementTree.tostring(rels, encoding="unicode"))

        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            '<row r="1"><c r="A1" t="inlineStr"><is><t>Col1</t></is></c></row>'
            '<row r="2"><c r="A2"><v>1</v></c></row>'
            "</sheetData>"
            "</worksheet>"
        )
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

        shared_strings = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="0"/>'
        )
        zf.writestr("xl/sharedStrings.xml", shared_strings)

    xlsx_content = buf.getvalue()

    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("ads_data.xlsx", xlsx_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["upload_id"]
    assert data["filename"] == "ads_data.xlsx"
    assert data["row_count"] == 1
    assert data["status"] == "initialized"


# ---------------------------------------------------------------------------
# Role-based access
# ---------------------------------------------------------------------------


def test_write_roles_can_upload() -> None:
    for role in ["owner", "admin", "analyst"]:
        workspace_id = str(uuid4())
        content = b"Col1\nA\n"
        response = client.post(
            f"/v1/workspaces/{workspace_id}/file-uploads",
            headers=auth_headers(workspace_id, role=role),
            files={"file": (f"{role}.csv", content, "text/csv")},
        )
        assert response.status_code == 201, f"Role {role} should be able to upload"


def test_readonly_roles_cannot_upload() -> None:
    for role in ["approver", "viewer"]:
        workspace_id = str(uuid4())
        content = b"Col1\nA\n"
        response = client.post(
            f"/v1/workspaces/{workspace_id}/file-uploads",
            headers=auth_headers(workspace_id, role=role),
            files={"file": (f"{role}.csv", content, "text/csv")},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "WORKSPACE_ROLE_FORBIDDEN"


# ---------------------------------------------------------------------------
# Validation: no file field
# ---------------------------------------------------------------------------


def test_rejects_request_without_file_field() -> None:
    workspace_id = str(uuid4())
    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
    )
    # Either multipart error or explicit error
    assert response.status_code in (400, 422)
    error_code = response.json()["error"]["code"]
    assert error_code in ("REPORT_FILE_REQUIRED", "MULTIPART_UPLOAD_REQUIRED", "VALIDATION_ERROR")


# ---------------------------------------------------------------------------
# Validation: unsupported file types
# ---------------------------------------------------------------------------


def test_rejects_pdf_file() -> None:
    workspace_id = str(uuid4())
    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("report.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_UPLOAD_MIME_TYPE"


def test_rejects_json_file() -> None:
    workspace_id = str(uuid4())
    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("data.json", b'{"key": "value"}', "application/json")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_UPLOAD_MIME_TYPE"


def test_rejects_unsupported_extension() -> None:
    workspace_id = str(uuid4())
    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 400
    error_code = response.json()["error"]["code"]
    assert error_code in ("UNSUPPORTED_UPLOAD_MIME_TYPE", "UNSUPPORTED_UPLOAD_EXTENSION")


# ---------------------------------------------------------------------------
# Validation: empty / zero-byte files
# ---------------------------------------------------------------------------


def test_rejects_zero_byte_file() -> None:
    workspace_id = str(uuid4())
    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REPORT_FILE_EMPTY"


def test_rejects_empty_csv_file() -> None:
    workspace_id = str(uuid4())
    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("empty.csv", b"Campaign,Impressions\n", "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UPLOAD_PARSE_EMPTY_FILE"


# ---------------------------------------------------------------------------
# Validation: unreadable/corrupt Excel
# ---------------------------------------------------------------------------


def test_rejects_corrupt_xlsx() -> None:
    workspace_id = str(uuid4())
    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={
            "file": (
                "corrupt.xlsx",
                b"PK\x03\x04not a real xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 400
    error_code = response.json()["error"]["code"]
    assert error_code in ("UPLOAD_PARSE_INVALID_XLSX", "UPLOAD_PARSE_EMPTY_FILE", "UPLOAD_PARSE_INVALID_FILE")


# ---------------------------------------------------------------------------
# Validation: filename path traversal
# ---------------------------------------------------------------------------


def test_rejects_filename_with_path_traversal() -> None:
    workspace_id = str(uuid4())
    content = b"Col1\nA\n"
    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("../etc/passwd.csv", content, "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD_FILENAME"


# ---------------------------------------------------------------------------
# Validation: file size
# ---------------------------------------------------------------------------


def test_rejects_oversized_file(monkeypatch) -> None:
    """Upload a file larger than the MVP limit."""
    from apps.api.app.domain.uploads import MAX_UPLOAD_FILE_SIZE_BYTES

    workspace_id = str(uuid4())
    content = b"x" * (MAX_UPLOAD_FILE_SIZE_BYTES + 1)
    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("huge.csv", content, "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UPLOAD_FILE_TOO_LARGE"


# ---------------------------------------------------------------------------
# Does NOT trigger analysis
# ---------------------------------------------------------------------------


def test_upload_does_not_create_workflow() -> None:
    """Verify the upload-only endpoint does not create workflows or account imports."""
    workspace_id = str(uuid4())
    content = b"Campaign,Impressions\nCamp1,100\n"

    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("report.csv", content, "text/csv")},
    )

    assert response.status_code == 201
    data = response.json()["data"]

    # The upload ID should exist, but no workflow should have been created
    upload_id = data["upload_id"]

    # Check that no workflows exist for this workspace
    workflows_response = client.get(
        f"/v1/workspaces/{workspace_id}/workflows",
        headers=auth_headers(workspace_id, role="viewer"),
    )
    if workflows_response.status_code == 200:
        workflows = workflows_response.json().get("data", [])
        # None of the workflows should reference our upload
        for wf in workflows:
            workflow_detail = client.get(
                f"/v1/workspaces/{workspace_id}/workflows/{wf['id']}",
                headers=auth_headers(workspace_id, role="viewer"),
            ).json()
            state = workflow_detail.get("data", {}).get("workflow", {}).get("state_json", {})
            assert state.get("upload_id") != upload_id, "Upload-only endpoint must not trigger workflows"

    # Also verify no account_import was created for this upload
    imports_response = client.get(
        f"/v1/workspaces/{workspace_id}/account-imports",
        headers=auth_headers(workspace_id, role="viewer"),
    )
    if imports_response.status_code == 200:
        imports_data = imports_response.json().get("data", [])
        for imp in imports_data:
            assert str(imp.get("upload_id")) != upload_id, "Upload-only endpoint must not create account imports"


# ---------------------------------------------------------------------------
# Subsequent retrieval
# ---------------------------------------------------------------------------


def test_upload_status_is_initialized_not_queued() -> None:
    """After upload-only, the status should stay 'initialized', not 'queued_for_processing'."""
    workspace_id = str(uuid4())
    content = b"Col1\nVal1\n"

    response = client.post(
        f"/v1/workspaces/{workspace_id}/file-uploads",
        headers=auth_headers(workspace_id),
        files={"file": ("simple.csv", content, "text/csv")},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "initialized"
    assert data["status"] != "queued_for_processing"