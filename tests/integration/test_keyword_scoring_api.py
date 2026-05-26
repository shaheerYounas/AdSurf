from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.app.core.config import get_settings
from apps.api.app.main import app
from apps.api.app.repositories.audit_logs import get_audit_log_repository
from apps.api.app.repositories.jobs import get_job_repository
from apps.api.app.schemas.jobs import JobStatus
from apps.api.app.services.storage import LocalFakeStorageService
from apps.api.app.services.upload_processing_worker import UploadProcessingWorker


client = TestClient(app)


def auth_headers(workspace_id: str, role: str = "owner", user_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {"x-user-id": user_id, "x-test-workspaces": f"{workspace_id}:{role}"}


def test_scoring_requires_approved_mapping(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_scoring_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]
    valid_mapping = _create_mapping(workspace_id, upload_id, profile["id"], _valid_mapping_json()).json()["data"]
    invalid_mapping = _create_mapping(
        workspace_id,
        upload_id,
        profile["id"],
        {"search_term": "Search Term", "search_volume": "Search Term", "competitor_rank_columns": ["Rank 1"]},
    ).json()["data"]

    draft_response = _score(workspace_id, valid_mapping["id"])
    invalid_response = _score(workspace_id, invalid_mapping["id"])

    assert draft_response.status_code == 409
    assert draft_response.json()["error"]["code"] == "COLUMN_MAPPING_NOT_APPROVED"
    assert invalid_response.status_code == 409
    assert invalid_response.json()["error"]["code"] == "COLUMN_MAPPING_NOT_APPROVED"


def test_owner_admin_analyst_can_trigger_scoring_and_viewer_approver_cannot(monkeypatch, tmp_path) -> None:
    for role in ["owner", "admin", "analyst"]:
        workspace_id, mapping = _approved_mapping(monkeypatch, tmp_path)
        response = _score(workspace_id, mapping["id"], role=role)
        assert response.status_code == 200

    for role in ["viewer", "approver"]:
        workspace_id, mapping = _approved_mapping(monkeypatch, tmp_path)
        response = _score(workspace_id, mapping["id"], role=role)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "WORKSPACE_ROLE_FORBIDDEN"


def test_scoring_creates_candidates_with_thresholds_and_preserves_duplicates(monkeypatch, tmp_path) -> None:
    workspace_id, mapping = _approved_mapping(monkeypatch, tmp_path)

    response = _score(workspace_id, mapping["id"])

    assert response.status_code == 200
    summary = response.json()["data"]
    assert summary["total_rows"] == 7
    assert summary["approved_count"] == 2
    assert summary["rejected_count"] == 3
    assert summary["error_count"] == 2

    candidates = client.get(
        f"/v1/workspaces/{workspace_id}/scoring-runs/{summary['scoring_run_id']}/candidates?page=1&page_size=20",
        headers=auth_headers(workspace_id),
    ).json()["data"]
    alpha_candidates = [candidate for candidate in candidates if candidate["search_term"] == "alpha"]
    beta = next(candidate for candidate in candidates if candidate["search_term"] == "beta")
    gamma = next(candidate for candidate in candidates if candidate["search_term"] == "gamma")
    empty_term = next(candidate for candidate in candidates if candidate["rejection_reason"] == "missing_search_term")

    assert len(alpha_candidates) == 2
    assert {candidate["relevance_score"] for candidate in alpha_candidates} == {3}
    assert beta["relevance_score"] == 2
    assert beta["scoring_status"] == "rejected"
    assert gamma["relevance_score"] == 1
    assert empty_term["scoring_status"] == "error"


def test_candidate_endpoint_filters_and_paginates(monkeypatch, tmp_path) -> None:
    workspace_id, mapping = _approved_mapping(monkeypatch, tmp_path)
    scoring_run_id = _score(workspace_id, mapping["id"]).json()["data"]["scoring_run_id"]

    approved = client.get(
        f"/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates?scoring_status=approved&page=1&page_size=1",
        headers=auth_headers(workspace_id),
    )
    score_two = client.get(
        f"/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates?min_relevance_score=2&max_relevance_score=2",
        headers=auth_headers(workspace_id),
    )
    alpha = client.get(
        f"/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates?search_term=alpha",
        headers=auth_headers(workspace_id),
    )

    assert approved.status_code == 200
    assert approved.json()["meta"]["total"] == 2
    assert approved.json()["meta"]["has_next"] is True
    assert score_two.json()["meta"]["total"] == 1
    assert alpha.json()["meta"]["total"] == 2


def test_scoring_idempotency_replay_and_mismatch(monkeypatch, tmp_path) -> None:
    workspace_id, upload_id = _processed_scoring_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]
    first_mapping = _approve_mapping(workspace_id, _create_mapping(workspace_id, upload_id, profile["id"], _valid_mapping_json()).json()["data"])
    key = str(uuid4())

    first = _score(workspace_id, first_mapping["id"], key=key)
    replay = _score(workspace_id, first_mapping["id"], key=key)
    second_mapping = _approve_mapping(workspace_id, _create_mapping(workspace_id, upload_id, profile["id"], _valid_mapping_json()).json()["data"])
    mismatch = _score(workspace_id, second_mapping["id"], key=key)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["data"]["scoring_run_id"] == first.json()["data"]["scoring_run_id"]
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    audit_repository = get_audit_log_repository()
    run_id = UUID(first.json()["data"]["scoring_run_id"])
    workspace_uuid = UUID(workspace_id)
    assert audit_repository.count(workspace_id=workspace_uuid, event_type="keyword_scoring.started", object_id=run_id) == 1
    assert audit_repository.count(workspace_id=workspace_uuid, event_type="keyword_scoring.completed", object_id=run_id) == 1


def test_cross_workspace_scoring_is_blocked(monkeypatch, tmp_path) -> None:
    workspace_a, mapping = _approved_mapping(monkeypatch, tmp_path)
    workspace_b = str(uuid4())

    response = _score(workspace_b, mapping["id"])
    get_response = client.get(f"/v1/workspaces/{workspace_b}/scoring-runs/{uuid4()}", headers=auth_headers(workspace_b))

    assert workspace_a != workspace_b
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COLUMN_MAPPING_NOT_FOUND"
    assert get_response.status_code == 404


def test_scoring_requires_idempotency_key(monkeypatch, tmp_path) -> None:
    workspace_id, mapping = _approved_mapping(monkeypatch, tmp_path)

    response = client.post(f"/v1/workspaces/{workspace_id}/column-mappings/{mapping['id']}/score", headers=auth_headers(workspace_id))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def _approved_mapping(monkeypatch, tmp_path) -> tuple[str, dict]:
    workspace_id, upload_id = _processed_scoring_upload(monkeypatch, tmp_path)
    profile = _generate_profile(workspace_id, upload_id).json()["data"]["profile"]
    mapping = _create_mapping(workspace_id, upload_id, profile["id"], _valid_mapping_json()).json()["data"]
    return workspace_id, _approve_mapping(workspace_id, mapping)


def _processed_scoring_upload(monkeypatch, tmp_path) -> tuple[str, str]:
    content = (
        "Search Term,Search Volume,Rank 1,Rank 2,Rank 3\n"
        "alpha,100,1,2,3\n"
        "beta,90,1,14,15\n"
        "gamma,80,14,15,\n"
        "delta,70,15,,20\n"
        "alpha,60,1,2,3\n"
        "negative,-1,1,2,3\n"
        ",50,1,2,3\n"
    )
    return _processed_upload(monkeypatch, tmp_path, content=content.encode("utf-8"))


def _processed_upload(monkeypatch, tmp_path, *, content: bytes) -> tuple[str, str]:
    storage_root = tmp_path / "s"
    monkeypatch.setenv("LOCAL_UPLOAD_STORAGE_ROOT", str(storage_root))
    get_settings.cache_clear()
    _cancel_existing_queued_jobs()
    workspace_id = str(uuid4())
    product_id = _create_product(workspace_id)
    upload = _init_upload(workspace_id, product_id).json()["data"]
    LocalFakeStorageService(root=str(storage_root)).write_upload_object(storage_path=upload["storage_path"], content=content)
    confirm_response = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload['upload_id']}/confirm",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={},
    )
    assert confirm_response.status_code == 200
    result = UploadProcessingWorker().process_one()
    assert result.processed is True
    return workspace_id, upload["upload_id"]


def _create_product(workspace_id: str) -> str:
    response = client.post(
        f"/v1/workspaces/{workspace_id}/products",
        headers=auth_headers(workspace_id),
        json={"product_name": f"Scoring Product {uuid4()}"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _init_upload(workspace_id: str, product_id: str):
    response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/uploads/init",
        headers={**auth_headers(workspace_id), "Idempotency-Key": str(uuid4())},
        json={
            "original_filename": "scoring.csv",
            "mime_type": "text/csv",
            "file_size_bytes": 1000,
            "source_type": "competitor_keyword_research",
        },
    )
    assert response.status_code == 201
    return response


def _generate_profile(workspace_id: str, upload_id: str):
    response = client.post(f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-profile", headers=auth_headers(workspace_id, role="analyst"))
    assert response.status_code == 200
    return response


def _create_mapping(workspace_id: str, upload_id: str, profile_id: str, mapping_json: dict):
    response = client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"column_profile_id": profile_id, "mapping_json": mapping_json},
    )
    assert response.status_code == 200
    return response


def _approve_mapping(workspace_id: str, mapping: dict) -> dict:
    response = client.post(f"/v1/workspaces/{workspace_id}/column-mappings/{mapping['id']}/approve", headers=auth_headers(workspace_id, role="analyst"))
    assert response.status_code == 200
    return response.json()["data"]


def _score(workspace_id: str, mapping_id: str, *, role: str = "analyst", key: str | None = None):
    return client.post(
        f"/v1/workspaces/{workspace_id}/column-mappings/{mapping_id}/score",
        headers={**auth_headers(workspace_id, role=role), "Idempotency-Key": key or str(uuid4())},
    )


def _valid_mapping_json() -> dict:
    return {
        "search_term": "Search Term",
        "search_volume": "Search Volume",
        "competitor_rank_columns": ["Rank 1", "Rank 2", "Rank 3"],
    }


def _cancel_existing_queued_jobs() -> None:
    repository = get_job_repository()
    for workspace_id, jobs in list(repository._jobs.items()):
        for job_id, job in list(jobs.items()):
            if job.status == JobStatus.QUEUED:
                repository.update_status(workspace_id=workspace_id, job_id=job_id, status=JobStatus.CANCELLED)
