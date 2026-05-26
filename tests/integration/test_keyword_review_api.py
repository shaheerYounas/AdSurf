from uuid import UUID, uuid4

from apps.api.app.repositories.audit_logs import get_audit_log_repository

from tests.integration.test_keyword_scoring_api import _approved_mapping, _score, auth_headers, client


def test_owner_admin_analyst_can_create_override_and_viewer_approver_cannot(monkeypatch, tmp_path) -> None:
    for role in ["owner", "admin", "analyst"]:
        workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
        rejected = _candidate_by_status(workspace_id, scoring_run_id, "rejected")

        response = _override(workspace_id, rejected["id"], "approve", role=role)

        assert response.status_code == 200
        assert response.json()["data"]["new_status"] == "approved"

    for role in ["viewer", "approver"]:
        workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
        rejected = _candidate_by_status(workspace_id, scoring_run_id, "rejected")

        response = _override(workspace_id, rejected["id"], "approve", role=role)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "WORKSPACE_ROLE_FORBIDDEN"


def test_override_requires_reason_and_blocks_error_candidates(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    rejected = _candidate_by_status(workspace_id, scoring_run_id, "rejected")
    error = _candidate_by_status(workspace_id, scoring_run_id, "error")

    missing_reason = _override(workspace_id, rejected["id"], "approve", reason="")
    whitespace_reason = _override(workspace_id, rejected["id"], "approve", reason="   ")
    error_response = _override(workspace_id, error["id"], "approve")

    assert missing_reason.status_code == 400
    assert missing_reason.json()["error"]["code"] == "OVERRIDE_REASON_REQUIRED"
    assert whitespace_reason.status_code == 400
    assert whitespace_reason.json()["error"]["code"] == "OVERRIDE_REASON_REQUIRED"
    assert error_response.status_code == 409
    assert error_response.json()["error"]["code"] == "KEYWORD_CANDIDATE_NOT_OVERRIDABLE"


def test_override_changes_effective_status_and_duplicate_same_status_returns_conflict(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    rejected = _candidate_by_status(workspace_id, scoring_run_id, "rejected")
    approved = _candidate_by_status(workspace_id, scoring_run_id, "approved")

    approve_response = _override(workspace_id, rejected["id"], "approve", reason="Relevant manual review")
    reject_response = _override(workspace_id, approved["id"], "reject", reason="Not relevant after review")
    noop_response = _override(workspace_id, approved["id"], "approve", reason="Already approved")

    assert approve_response.status_code == 200
    assert reject_response.status_code == 200
    assert noop_response.status_code == 409
    assert noop_response.json()["error"]["code"] == "KEYWORD_CANDIDATE_OVERRIDE_EXISTS"

    reviews = _reviews(workspace_id, scoring_run_id).json()["data"]
    approved_review = next(review for review in reviews if review["id"] == rejected["id"])
    rejected_review = next(review for review in reviews if review["id"] == approved["id"])

    assert approved_review["original_scoring_status"] == "rejected"
    assert approved_review["effective_status"] == "approved"
    assert approved_review["override"]["reason"] == "Relevant manual review"
    assert rejected_review["original_scoring_status"] == "approved"
    assert rejected_review["effective_status"] == "rejected"


def test_review_endpoint_filters_by_effective_status(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    rejected = _candidate_by_status(workspace_id, scoring_run_id, "rejected")
    _override(workspace_id, rejected["id"], "approve")

    approved = _reviews(workspace_id, scoring_run_id, effective_status="approved")
    has_override = _reviews(workspace_id, scoring_run_id, has_override="true")

    assert approved.status_code == 200
    assert any(review["id"] == rejected["id"] and review["effective_status"] == "approved" for review in approved.json()["data"])
    assert has_override.json()["meta"]["total"] == 1


def test_approved_keyword_set_snapshot_includes_effective_approved_only_and_paginates(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    rejected = _candidate_by_term(workspace_id, scoring_run_id, "beta")
    approved = _candidate_by_term(workspace_id, scoring_run_id, "alpha")
    approve_override = _override(workspace_id, rejected["id"], "approve", reason="Manual rank acceptance").json()["data"]
    reject_override = _override(workspace_id, approved["id"], "reject", reason="Duplicate not wanted").json()["data"]

    response = _create_keyword_set(workspace_id, scoring_run_id, name="Reviewed keywords")
    keyword_set = response.json()["data"]
    items = _keyword_set_items(workspace_id, keyword_set["id"], page_size=1)
    all_items = _keyword_set_items(workspace_id, keyword_set["id"], page_size=20).json()["data"]

    assert response.status_code == 200
    assert keyword_set["status"] == "locked"
    assert keyword_set["keyword_count"] == 2
    assert items.json()["meta"]["total"] == 2
    assert items.json()["meta"]["has_next"] is True
    assert any(item["keyword_candidate_id"] == rejected["id"] and item["override_id"] == approve_override["id"] for item in all_items)
    assert all(item["keyword_candidate_id"] != approved["id"] for item in all_items)
    assert reject_override["new_status"] == "rejected"


def test_approved_keyword_set_requires_at_least_one_effective_approved_candidate(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    for candidate in _reviews(workspace_id, scoring_run_id, effective_status="approved").json()["data"]:
        _override(workspace_id, candidate["id"], "reject", reason="Exclude all approved")

    response = _create_keyword_set(workspace_id, scoring_run_id, name="Empty set")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVED_KEYWORD_SET_EMPTY"


def test_approved_keyword_set_snapshot_does_not_change_after_later_override(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    first = _create_keyword_set(workspace_id, scoring_run_id, name="Snapshot").json()["data"]
    first_items = _keyword_set_items(workspace_id, first["id"], page_size=20).json()["data"]
    rejected = _candidate_by_term(workspace_id, scoring_run_id, "beta")

    _override(workspace_id, rejected["id"], "approve", reason="Include later")
    after_items = _keyword_set_items(workspace_id, first["id"], page_size=20).json()["data"]

    assert len(first_items) == 2
    assert after_items == first_items


def test_cross_workspace_override_and_keyword_set_access_are_blocked(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    other_workspace_id = str(uuid4())
    candidate = _candidate_by_status(workspace_id, scoring_run_id, "rejected")
    keyword_set = _create_keyword_set(workspace_id, scoring_run_id, name="Scoped set").json()["data"]

    override_response = _override(other_workspace_id, candidate["id"], "approve")
    set_response = client.get(f"/v1/workspaces/{other_workspace_id}/approved-keyword-sets/{keyword_set['id']}", headers=auth_headers(other_workspace_id))

    assert override_response.status_code == 404
    assert override_response.json()["error"]["code"] == "KEYWORD_CANDIDATE_NOT_FOUND"
    assert set_response.status_code == 404


def test_review_audit_events_are_created_once_per_action(monkeypatch, tmp_path) -> None:
    workspace_id, scoring_run_id = _scored_run(monkeypatch, tmp_path)
    candidate = _candidate_by_status(workspace_id, scoring_run_id, "rejected")
    override = _override(workspace_id, candidate["id"], "approve").json()["data"]
    keyword_set = _create_keyword_set(workspace_id, scoring_run_id, name="Audited set").json()["data"]
    audit_repository = get_audit_log_repository()
    workspace_uuid = UUID(workspace_id)

    assert audit_repository.count(workspace_id=workspace_uuid, event_type="keyword_candidate.override_created", object_id=UUID(override["id"])) == 1
    assert audit_repository.count(workspace_id=workspace_uuid, event_type="approved_keyword_set.created", object_id=UUID(keyword_set["id"])) == 1


def _scored_run(monkeypatch, tmp_path) -> tuple[str, str]:
    workspace_id, mapping = _approved_mapping(monkeypatch, tmp_path)
    score_response = _score(workspace_id, mapping["id"])
    assert score_response.status_code == 200
    return workspace_id, score_response.json()["data"]["scoring_run_id"]


def _reviews(workspace_id: str, scoring_run_id: str, **filters):
    params = {"page": "1", "page_size": "20", **{key: value for key, value in filters.items() if value is not None}}
    return client.get(
        f"/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates/review",
        headers=auth_headers(workspace_id),
        params=params,
    )


def _candidate_by_status(workspace_id: str, scoring_run_id: str, status: str) -> dict:
    response = _reviews(workspace_id, scoring_run_id, effective_status=status)
    assert response.status_code == 200
    return response.json()["data"][0]


def _candidate_by_term(workspace_id: str, scoring_run_id: str, term: str) -> dict:
    response = _reviews(workspace_id, scoring_run_id)
    assert response.status_code == 200
    return next(candidate for candidate in response.json()["data"] if candidate["search_term"] == term)


def _override(workspace_id: str, candidate_id: str, action: str, *, role: str = "analyst", reason: str = "Manual review reason"):
    return client.post(
        f"/v1/workspaces/{workspace_id}/keyword-candidates/{candidate_id}/override",
        headers=auth_headers(workspace_id, role=role),
        json={"override_action": action, "reason": reason},
    )


def _create_keyword_set(workspace_id: str, scoring_run_id: str, *, name: str):
    return client.post(
        f"/v1/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/approved-keyword-sets",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"name": name},
    )


def _keyword_set_items(workspace_id: str, keyword_set_id: str, *, page_size: int):
    return client.get(
        f"/v1/workspaces/{workspace_id}/approved-keyword-sets/{keyword_set_id}/items?page=1&page_size={page_size}",
        headers=auth_headers(workspace_id),
    )
