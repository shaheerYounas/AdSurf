from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.app.main import app
from apps.api.app.repositories.audit_logs import get_audit_log_repository
from apps.api.app.repositories.jobs import get_job_repository
from apps.api.app.repositories.uploads import get_upload_repository
from apps.api.app.schemas.uploads import UploadStatus


client = TestClient(app)


def auth_headers(workspace_id: str, role: str = "owner", user_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "x-user-id": user_id,
        "x-test-workspaces": f"{workspace_id}:{role}",
    }


def create_product(workspace_id: str) -> str:
    response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id, role="owner"),
        json={"product_name": f"Upload Product {uuid4()}"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def init_payload(**overrides: object) -> dict:
    payload = {
        "original_filename": "competitor-keywords.csv",
        "mime_type": "text/csv",
        "file_size_bytes": 1024,
        "source_type": "competitor_keyword_research",
    }
    payload.update(overrides)
    return payload


def init_upload(workspace_id: str, product_id: str, key: str | None = None, **overrides: object):
    return client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": key or str(uuid4())},
        json=init_payload(**overrides),
    )


def test_init_upload_success_returns_signed_target() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)

    response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id, role="analyst"), "Idempotency-Key": str(uuid4())},
        json=init_payload(original_filename="Competitor Report.csv"),
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "initialized"
    assert data["upload_url"].startswith("local-fake://signed-upload/")
    assert data["storage_path"].startswith(f"/workspaces/{workspace_id}/products/{product_id}/uploads/")
    assert data["storage_path"].endswith("/raw/Competitor_Report.csv")


def test_init_upload_rejects_unsupported_mime_type() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)

    response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json=init_payload(mime_type="application/pdf"),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_UPLOAD_MIME_TYPE"


def test_init_upload_rejects_unsupported_extension() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)

    response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json=init_payload(original_filename="competitor-keywords.txt"),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_UPLOAD_EXTENSION"


def test_init_upload_rejects_file_too_large() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)

    response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json=init_payload(file_size_bytes=25 * 1024 * 1024 + 1),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UPLOAD_FILE_TOO_LARGE"


def test_init_upload_requires_idempotency_key() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)

    response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers=auth_headers(workspace_id),
        json=init_payload(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_duplicate_init_idempotency_key_returns_existing_upload_for_same_request() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)
    key = str(uuid4())

    first = init_upload(workspace_id, product_id, key=key, original_filename="same.csv")
    second = init_upload(workspace_id, product_id, key=key, original_filename="same.csv")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["data"]["upload_id"] == first.json()["data"]["upload_id"]
    assert second.json()["data"]["storage_path"] == first.json()["data"]["storage_path"]


def test_duplicate_init_idempotency_key_rejects_different_product() -> None:
    workspace_id = str(uuid4())
    product_a = create_product(workspace_id)
    product_b = create_product(workspace_id)
    key = str(uuid4())

    first = init_upload(workspace_id, product_a, key=key, original_filename="same.csv")
    second = init_upload(workspace_id, product_b, key=key, original_filename="same.csv")

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_duplicate_init_idempotency_key_rejects_identity_mismatches() -> None:
    cases = [
        {"original_filename": "other.csv"},
        {"mime_type": "application/vnd.ms-excel"},
        {"file_size_bytes": 2048},
        {"source_type": "monitoring_report"},
    ]

    for override in cases:
        workspace_id = str(uuid4())
        product_id = create_product(workspace_id)
        key = str(uuid4())

        replay_payload = {"original_filename": "same.csv", **override}
        first = init_upload(workspace_id, product_id, key=key, original_filename="same.csv")
        second = init_upload(workspace_id, product_id, key=key, **replay_payload)

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_duplicate_init_after_upload_is_queued_returns_conflict() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)
    key = str(uuid4())
    init_response = init_upload(workspace_id, product_id, key=key, original_filename="queued.csv")
    upload_id = init_response.json()["data"]["upload_id"]

    confirm = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={},
    )
    replay = init_upload(workspace_id, product_id, key=key, original_filename="queued.csv")

    assert confirm.status_code == 200
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_cross_workspace_product_upload_init_is_blocked() -> None:
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    product_a = create_product(workspace_a)

    response = init_upload(workspace_b, product_a, original_filename="wrong-workspace.csv")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_upload_write_roles() -> None:
    for role in ["owner", "admin", "analyst"]:
        workspace_id = str(uuid4())
        product_id = create_product(workspace_id)
        response = client.post(
            f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
            headers={**auth_headers(workspace_id, role=role), "Idempotency-Key": str(uuid4())},
            json=init_payload(original_filename=f"{role}.csv"),
        )
        assert response.status_code == 201

    for role in ["approver", "viewer"]:
        workspace_id = str(uuid4())
        product_id = create_product(workspace_id)
        response = client.post(
            f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
            headers={**auth_headers(workspace_id, role=role), "Idempotency-Key": str(uuid4())},
            json=init_payload(original_filename=f"{role}.csv"),
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "WORKSPACE_ROLE_FORBIDDEN"


def test_confirm_upload_enqueues_one_job_and_is_idempotent() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)
    init_response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id, role="admin"), "Idempotency-Key": str(uuid4())},
        json=init_payload(original_filename="confirm-me.xlsx", mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    )
    upload_id = init_response.json()["data"]["upload_id"]

    first_confirm = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm",
        headers={**auth_headers(workspace_id, role="admin"), "Idempotency-Key": str(uuid4())},
        json={},
    )
    second_confirm = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm",
        headers={**auth_headers(workspace_id, role="admin"), "Idempotency-Key": str(uuid4())},
        json={},
    )

    assert first_confirm.status_code == 200
    assert second_confirm.status_code == 200
    assert first_confirm.json()["data"]["status"] == "queued_for_processing"
    assert second_confirm.json()["data"]["job_id"] == first_confirm.json()["data"]["job_id"]

    job_id = first_confirm.json()["data"]["job_id"]
    job_response = client.get(f"/v1/workspaces/{workspace_id}/jobs/{job_id}", headers=auth_headers(workspace_id, role="viewer"))
    assert job_response.status_code == 200
    job = job_response.json()["data"]
    assert job["job_type"] == "process_upload"
    assert job["status"] == "queued"
    assert job["payload_json"]["upload_id"] == upload_id

    job_repository = get_job_repository()
    audit_repository = get_audit_log_repository()
    workspace_uuid = UUID(workspace_id)
    job_count = sum(
        1
        for job_record in job_repository._jobs[workspace_uuid].values()
        if job_record.job_type == "process_upload" and job_record.payload_json["upload_id"] == upload_id
    )
    assert job_count == 1
    assert audit_repository.count(workspace_id=workspace_uuid, event_type="job.queued", object_id=UUID(job_id)) == 1


def test_confirm_upload_rejects_terminal_or_active_states_without_enqueueing() -> None:
    blocked_statuses = [
        UploadStatus.UPLOADED,
        UploadStatus.PROCESSING,
        UploadStatus.PROCESSED,
        UploadStatus.FAILED,
        UploadStatus.CANCELLED,
    ]

    for blocked_status in blocked_statuses:
        workspace_id = str(uuid4())
        product_id = create_product(workspace_id)
        init_response = init_upload(workspace_id, product_id, original_filename=f"{blocked_status.value}.csv")
        upload_id = init_response.json()["data"]["upload_id"]
        _set_local_upload_status(workspace_id=workspace_id, upload_id=upload_id, status=blocked_status)

        response = client.post(
            f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm",
            headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
            json={},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "UPLOAD_NOT_CONFIRMABLE"


def test_confirm_upload_rejects_queued_upload_without_existing_job() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)
    init_response = init_upload(workspace_id, product_id, original_filename="queued-no-job.csv")
    upload_id = init_response.json()["data"]["upload_id"]
    _set_local_upload_status(workspace_id=workspace_id, upload_id=upload_id, status=UploadStatus.QUEUED_FOR_PROCESSING)

    response = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "UPLOAD_NOT_CONFIRMABLE"


def test_cross_workspace_upload_access_is_blocked() -> None:
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    product_id = create_product(workspace_a)
    init_response = client.post(
        f"/v1/workspaces/{workspace_a}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_a), "Idempotency-Key": str(uuid4())},
        json=init_payload(),
    )
    upload_id = init_response.json()["data"]["upload_id"]

    get_response = client.get(f"/v1/workspaces/{workspace_b}/uploads/{upload_id}", headers=auth_headers(workspace_b))
    confirm_response = client.post(
        f"/v1/workspaces/{workspace_b}/uploads/{upload_id}/confirm",
        headers={**auth_headers(workspace_b), "Idempotency-Key": str(uuid4())},
        json={},
    )

    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert confirm_response.status_code == 404
    assert confirm_response.json()["error"]["code"] == "UPLOAD_NOT_FOUND"


def test_storage_path_sanitizes_filename_and_rejects_traversal() -> None:
    workspace_id = str(uuid4())
    product_id = create_product(workspace_id)
    good = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json=init_payload(original_filename="My Report (Final).CSV"),
    )
    bad = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json=init_payload(original_filename="../evil.csv"),
    )

    assert good.status_code == 201
    assert good.json()["data"]["storage_path"].endswith("/raw/My_Report_Final.csv")
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_UPLOAD_FILENAME"


def _set_local_upload_status(*, workspace_id: str, upload_id: str, status: UploadStatus) -> None:
    repository = get_upload_repository()
    workspace_uuid = UUID(workspace_id)
    upload_uuid = UUID(upload_id)
    current = repository.get(workspace_id=workspace_uuid, upload_id=upload_uuid)
    assert current is not None
    repository._uploads[workspace_uuid][upload_uuid] = current.model_copy(update={"status": status})
