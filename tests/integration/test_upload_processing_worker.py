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


def test_worker_success_updates_upload_job_and_parse_statuses(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_id = str(uuid4())
    product_id = _create_product(workspace_id)
    init_response = _init_upload(workspace_id, product_id, original_filename="worker.csv")
    upload = init_response.json()["data"]
    LocalFakeStorageService(root=str(tmp_path)).write_upload_object(
        storage_path=upload["storage_path"],
        content=b"term,bid\nshoes,1.25\nboots,\n",
    )
    confirm_response = _confirm_upload(workspace_id, upload["upload_id"])
    job_id = confirm_response.json()["data"]["job_id"]

    result = UploadProcessingWorker().process_one()

    assert result.processed is True
    upload_response = client.get(f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}", headers=auth_headers(workspace_id))
    job_response = client.get(f"/v1/workspaces/{workspace_id}/jobs/{job_id}", headers=auth_headers(workspace_id))
    runs_response = client.get(f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/parse-runs", headers=auth_headers(workspace_id))

    assert upload_response.json()["data"]["status"] == "processed"
    assert job_response.json()["data"]["status"] == "succeeded"
    parse_run = runs_response.json()["data"][0]
    assert parse_run["status"] == "succeeded"
    assert parse_run["parsed_rows_count"] == 2
    assert parse_run["error_rows_count"] == 0

    rows_response = client.get(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/parse-runs/{parse_run['id']}/rows?page=1&page_size=1",
        headers=auth_headers(workspace_id),
    )
    assert rows_response.status_code == 200
    assert rows_response.json()["meta"]["total"] == 2
    assert rows_response.json()["meta"]["has_next"] is True
    assert rows_response.json()["data"][0]["row_data_json"] == {"term": "shoes", "bid": "1.25"}


def test_archive_processed_upload_preserves_completed_job_and_parse_history(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_id = str(uuid4())
    product_id = _create_product(workspace_id)
    init_response = _init_upload(workspace_id, product_id, original_filename="archive-processed.csv")
    upload = init_response.json()["data"]
    LocalFakeStorageService(root=str(tmp_path)).write_upload_object(
        storage_path=upload["storage_path"],
        content=b"term,bid\nshoes,1.25\nboots,1.10\n",
    )
    confirm_response = _confirm_upload(workspace_id, upload["upload_id"])
    job_id = confirm_response.json()["data"]["job_id"]
    UploadProcessingWorker().process_one()
    runs_before = client.get(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/parse-runs",
        headers=auth_headers(workspace_id),
    ).json()["data"]

    archive_response = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/archive",
        headers=auth_headers(workspace_id),
    )

    job_response = client.get(f"/v1/workspaces/{workspace_id}/jobs/{job_id}", headers=auth_headers(workspace_id))
    runs_after = client.get(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/parse-runs",
        headers=auth_headers(workspace_id),
    )
    upload_response = client.get(f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}", headers=auth_headers(workspace_id))

    assert archive_response.status_code == 200
    assert archive_response.json()["data"]["status"] == "archived"
    assert job_response.status_code == 200
    assert job_response.json()["data"]["status"] == "succeeded"
    assert runs_after.status_code == 200
    assert [run["id"] for run in runs_after.json()["data"]] == [run["id"] for run in runs_before]
    assert upload_response.json()["data"]["status"] == "archived"


def test_worker_failure_updates_statuses_and_records_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_id = str(uuid4())
    product_id = _create_product(workspace_id)
    init_response = _init_upload(workspace_id, product_id, original_filename="empty.csv")
    upload = init_response.json()["data"]
    LocalFakeStorageService(root=str(tmp_path)).write_upload_object(storage_path=upload["storage_path"], content=b"")
    confirm_response = _confirm_upload(workspace_id, upload["upload_id"])
    job_id = confirm_response.json()["data"]["job_id"]

    result = UploadProcessingWorker().process_one()

    assert result.processed is True
    upload_response = client.get(f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}", headers=auth_headers(workspace_id))
    job_response = client.get(f"/v1/workspaces/{workspace_id}/jobs/{job_id}", headers=auth_headers(workspace_id))
    runs_response = client.get(f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/parse-runs", headers=auth_headers(workspace_id))
    parse_run = runs_response.json()["data"][0]
    errors_response = client.get(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/parse-runs/{parse_run['id']}/errors",
        headers=auth_headers(workspace_id),
    )

    assert upload_response.json()["data"]["status"] == "failed"
    assert job_response.json()["data"]["status"] == "failed"
    assert parse_run["status"] == "failed"
    assert parse_run["error_rows_count"] == 1
    assert errors_response.json()["data"][0]["error_code"] == "UPLOAD_PARSE_EMPTY_FILE"


def test_cross_workspace_parse_run_access_is_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    product_id = _create_product(workspace_a)
    init_response = _init_upload(workspace_a, product_id, original_filename="cross.csv")
    upload = init_response.json()["data"]
    LocalFakeStorageService(root=str(tmp_path)).write_upload_object(storage_path=upload["storage_path"], content=b"term\nshoes\n")
    _confirm_upload(workspace_a, upload["upload_id"])
    UploadProcessingWorker().process_one()
    runs = client.get(f"/v1/workspaces/{workspace_a}/uploads/{upload['upload_id']}/parse-runs", headers=auth_headers(workspace_a)).json()["data"]

    response = client.get(
        f"/v1/workspaces/{workspace_b}/uploads/{upload['upload_id']}/parse-runs/{runs[0]['id']}",
        headers=auth_headers(workspace_b),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UPLOAD_NOT_FOUND"


def _create_product(workspace_id: str) -> str:
    response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
        json={"product_name": f"Worker Product {uuid4()}"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _init_upload(workspace_id: str, product_id: str, *, original_filename: str):
    response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={
            "original_filename": original_filename,
            "mime_type": "text/csv",
            "file_size_bytes": 100,
            "source_type": "competitor_keyword_research",
        },
    )
    assert response.status_code == 201
    return response


def _confirm_upload(workspace_id: str, upload_id: str):
    response = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={},
    )
    assert response.status_code == 200
    return response


def _cancel_existing_queued_jobs() -> None:
    repository = get_job_repository()
    for workspace_id, jobs in list(repository._jobs.items()):
        for job_id, job in list(jobs.items()):
            if job.status == JobStatus.QUEUED:
                repository.update_status(workspace_id=workspace_id, job_id=job_id, status=JobStatus.CANCELLED)
