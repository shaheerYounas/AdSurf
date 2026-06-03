import io
import zipfile
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.app.core.config import get_settings
from apps.api.app.main import app
from apps.api.app.repositories.jobs import get_job_repository
from apps.api.app.schemas.jobs import JobStatus
from apps.api.app.services.storage import LocalFakeStorageService
from apps.api.app.services.upload_processing_worker import UploadProcessingWorker


client = TestClient(app)


def auth_headers(workspace_id: str, role: str = "owner", user_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "x-user-id": user_id,
        "x-test-workspaces": f"{workspace_id}:{role}",
    }


def test_column_profile_generation_success_preserves_and_normalizes_columns(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_csv_upload(monkeypatch, tmp_path, rows=25)

    response = _generate_profile(workspace_id, upload_id)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["profile"]["total_columns"] == 3
    assert data["profile"]["total_rows_sampled"] == 25
    columns = data["columns"]
    assert [column["original_column_name"] for column in columns] == ["Search Term", "Search Volume!", "Competitor Rank 1"]
    assert columns[1]["normalized_column_name"] == "search volume"
    assert len(columns[0]["sample_values_json"]) == 20
    assert columns[0]["inferred_data_type"] == "text"


def test_column_profile_generation_is_idempotent(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_csv_upload(monkeypatch, tmp_path)

    first = _generate_profile(workspace_id, upload_id)
    second = _generate_profile(workspace_id, upload_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["profile"]["id"] == first.json()["data"]["profile"]["id"]


def test_column_profile_is_blocked_before_successful_parse(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_id = str(uuid4())
    product_id = _create_product(workspace_id)
    upload = _init_upload(workspace_id, product_id, original_filename="unparsed.csv").json()["data"]

    response = _generate_profile(workspace_id, upload["upload_id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COLUMN_PROFILE_PARSE_RUN_REQUIRED"


def test_column_profile_infers_numeric_types_from_xlsx(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_xlsx_upload(monkeypatch, tmp_path)

    response = _generate_profile(workspace_id, upload_id)

    assert response.status_code == 200
    inferred_by_name = {column["original_column_name"]: column["inferred_data_type"] for column in response.json()["data"]["columns"]}
    assert inferred_by_name["Search Volume"] == "integer"
    assert inferred_by_name["Rank 1"] == "integer"


def test_column_profile_infers_xlsx_date_styles(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_upload(
        monkeypatch,
        tmp_path,
        original_filename="dated.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=_minimal_xlsx(
            data_sheet_xml="""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="inlineStr"><is><t>Search Term</t></is></c>
                  <c r="B1" t="inlineStr"><is><t>End Date</t></is></c>
                </row>
                <row r="2">
                  <c r="A2" t="inlineStr"><is><t>running shoes</t></is></c>
                  <c r="B2" s="1"><v>46149</v></c>
                </row>
              </sheetData>
            </worksheet>""",
            styles_xml=_date_styles_xml(),
        ),
    )

    response = _generate_profile(workspace_id, upload_id)

    assert response.status_code == 200
    columns = {column["original_column_name"]: column for column in response.json()["data"]["columns"]}
    assert columns["End Date"]["inferred_data_type"] == "date"
    assert columns["End Date"]["sample_values_json"] == ["2026-05-07"]


def test_manual_mapping_create_and_approve_valid_mapping(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_xlsx_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]
    create_response = _create_mapping(
        workspace_id,
        upload_id,
        profile["id"],
        {
            "search_term": "Search Term",
            "search_volume": "Search Volume",
            "competitor_rank_columns": ["Rank 1"],
        },
    )

    assert create_response.status_code == 200
    mapping = create_response.json()["data"]
    assert mapping["status"] == "valid"
    assert mapping["mapping_type"] == "manual"

    approve_response = client.post(
        f"/v1/workspaces/{workspace_id}/column-mappings/{mapping['id']}/approve",
        headers=auth_headers(workspace_id, role="analyst"),
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["data"]["status"] == "approved"


def test_manual_mapping_missing_fields_and_empty_rank_columns_are_invalid(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_xlsx_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]

    response = _create_mapping(workspace_id, upload_id, profile["id"], {"competitor_rank_columns": []})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "invalid"
    assert {message["code"] for message in data["validation_errors_json"]} >= {
        "MISSING_SEARCH_TERM",
        "MISSING_SEARCH_VOLUME",
        "MISSING_COMPETITOR_RANK_COLUMNS",
    }


def test_manual_mapping_duplicate_role_columns_are_invalid(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_xlsx_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]

    response = _create_mapping(
        workspace_id,
        upload_id,
        profile["id"],
        {
            "search_term": "Search Term",
            "search_volume": "Search Term",
            "competitor_rank_columns": ["Rank 1", "Rank 1"],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "invalid"
    assert "DUPLICATE_SEARCH_TERM_SEARCH_VOLUME" in {message["code"] for message in response.json()["data"]["validation_errors_json"]}


def test_manual_mapping_non_numeric_search_volume_is_invalid(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_xlsx_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]

    response = _create_mapping(
        workspace_id,
        upload_id,
        profile["id"],
        {
            "search_term": "Search Term",
            "search_volume": "Search Term",
            "competitor_rank_columns": ["Rank 1"],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "invalid"
    assert "SEARCH_VOLUME_NOT_NUMERIC" in {message["code"] for message in response.json()["data"]["validation_errors_json"]}


def test_manual_mapping_rejects_performance_metric_as_competitor_rank(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_csv_upload(
        monkeypatch,
        tmp_path,
        content="Customer Search Term,Impressions,Spend\nrunning shoes,1000,7.33\n",
    )
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]

    response = _create_mapping(
        workspace_id,
        upload_id,
        profile["id"],
        {
            "search_term": "Customer Search Term",
            "search_volume": "Impressions",
            "competitor_rank_columns": ["Spend"],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "invalid"
    assert "COMPETITOR_RANK_NAME_NOT_RANK_LIKE" in {message["code"] for message in data["validation_errors_json"]}


def test_numeric_like_text_mapping_is_allowed_with_warning(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_csv_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]

    response = _create_mapping(
        workspace_id,
        upload_id,
        profile["id"],
        {
            "search_term": "Search Term",
            "search_volume": "Search Volume!",
            "competitor_rank_columns": ["Competitor Rank 1"],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "valid"
    assert {message["severity"] for message in data["validation_errors_json"]} == {"warning"}


def test_approve_invalid_mapping_fails(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_xlsx_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]
    mapping = _create_mapping(
        workspace_id,
        upload_id,
        profile["id"],
        {"search_term": "Search Term", "search_volume": "Search Term", "competitor_rank_columns": ["Rank 1"]},
    ).json()["data"]

    response = client.post(
        f"/v1/workspaces/{workspace_id}/column-mappings/{mapping['id']}/approve",
        headers=auth_headers(workspace_id),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COLUMN_MAPPING_NOT_APPROVABLE"


def test_approving_mapping_supersedes_previous_approved_mapping(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_xlsx_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]
    payload = {"search_term": "Search Term", "search_volume": "Search Volume", "competitor_rank_columns": ["Rank 1"]}
    first = _create_mapping(workspace_id, upload_id, profile["id"], payload).json()["data"]
    second = _create_mapping(workspace_id, upload_id, profile["id"], payload).json()["data"]

    client.post(f"/v1/workspaces/{workspace_id}/column-mappings/{first['id']}/approve", headers=auth_headers(workspace_id))
    client.post(f"/v1/workspaces/{workspace_id}/column-mappings/{second['id']}/approve", headers=auth_headers(workspace_id))
    mappings = client.get(f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings", headers=auth_headers(workspace_id)).json()["data"]

    statuses = {mapping["id"]: mapping["status"] for mapping in mappings}
    assert statuses[first["id"]] == "superseded"
    assert statuses[second["id"]] == "approved"


def test_viewer_and_approver_cannot_create_column_mapping(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_xlsx_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]
    payload = {"search_term": "Search Term", "search_volume": "Search Volume", "competitor_rank_columns": ["Rank 1"]}

    for role in ["viewer", "approver"]:
        response = _create_mapping(workspace_id, upload_id, profile["id"], payload, role=role)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "WORKSPACE_ROLE_FORBIDDEN"


def test_cross_workspace_column_profile_access_is_blocked(monkeypatch, tmp_path) -> None:
    workspace_a, upload_id = _processed_xlsx_upload(monkeypatch, tmp_path)
    workspace_b = str(uuid4())

    response = client.get(f"/v1/workspaces/{workspace_b}/uploads/{upload_id}/column-profile", headers=auth_headers(workspace_b))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UPLOAD_NOT_FOUND"


def _processed_csv_upload(monkeypatch, tmp_path, rows: int = 2, content: str | None = None) -> tuple[str, str]:
    if content is None:
        content = "Search Term,Search Volume!,Competitor Rank 1\n"
        content += "".join(f"shoes {index},{100 + index},{index % 10 + 1}\n" for index in range(rows))
    return _processed_upload(
        monkeypatch,
        tmp_path,
        original_filename="k.csv",
        mime_type="text/csv",
        content=content.encode("utf-8"),
    )


def _processed_xlsx_upload(monkeypatch, tmp_path) -> tuple[str, str]:
    return _processed_upload(
        monkeypatch,
        tmp_path,
        original_filename="k.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=_minimal_xlsx(),
    )


def _processed_upload(monkeypatch, tmp_path, *, original_filename: str, mime_type: str, content: bytes) -> tuple[str, str]:
    storage_root = tmp_path / "s"
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(storage_root))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_id = str(uuid4())
    product_id = _create_product(workspace_id)
    upload = _init_upload(workspace_id, product_id, original_filename=original_filename, mime_type=mime_type).json()["data"]
    LocalFakeStorageService(root=str(storage_root)).write_upload_object(storage_path=upload["storage_path"], content=content)
    confirm_response = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/confirm",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={},
    )
    assert confirm_response.status_code == 200
    result = UploadProcessingWorker().process_one()
    assert result.processed is True
    assert result.parse_run is not None
    return workspace_id, upload["upload_id"]


def _create_product(workspace_id: str) -> str:
    response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
        json={"product_name": f"Mapping Product {uuid4()}"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _init_upload(workspace_id: str, product_id: str, *, original_filename: str, mime_type: str = "text/csv"):
    response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={
            "original_filename": original_filename,
            "mime_type": mime_type,
            "file_size_bytes": 1000,
            "source_type": "competitor_keyword_research",
        },
    )
    assert response.status_code == 201
    return response


def _generate_profile(workspace_id: str, upload_id: str):
    return client.post(f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-profile", headers=auth_headers(workspace_id, role="analyst"))


def _create_mapping(workspace_id: str, upload_id: str, profile_id: str, mapping_json: dict, role: str = "analyst"):
    return client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings",
        headers=auth_headers(workspace_id, role=role),
        json={"column_profile_id": profile_id, "mapping_json": mapping_json},
    )


def _cancel_existing_queued_jobs() -> None:
    repository = get_job_repository()
    for workspace_id, jobs in list(repository._jobs.items()):
        for job_id, job in list(jobs.items()):
            if job.status == JobStatus.QUEUED:
                repository.update_status(workspace_id=workspace_id, job_id=job_id, status=JobStatus.CANCELLED)


def _minimal_xlsx(*, data_sheet_xml: str | None = None, styles_xml: str | None = None) -> bytes:
    if data_sheet_xml is None:
        data_sheet_xml = """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData>
            <row r="1">
              <c r="A1" t="inlineStr"><is><t>Search Term</t></is></c>
              <c r="B1" t="inlineStr"><is><t>Search Volume</t></is></c>
              <c r="C1" t="inlineStr"><is><t>Rank 1</t></is></c>
            </row>
            <row r="2">
              <c r="A2" t="inlineStr"><is><t>running shoes</t></is></c>
              <c r="B2"><v>1000</v></c>
              <c r="C2"><v>3</v></c>
            </row>
          </sheetData>
        </worksheet>"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
            </workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            data_sheet_xml,
        )
        if styles_xml is not None:
            archive.writestr("xl/styles.xml", styles_xml)
    return output.getvalue()


def _date_styles_xml() -> str:
    return """<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <cellXfs count="2">
        <xf numFmtId="0"/>
        <xf numFmtId="14"/>
      </cellXfs>
    </styleSheet>"""
