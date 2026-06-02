from datetime import UTC, datetime
from uuid import uuid4

from apps.api.app.repositories.competitor_cleaned import LocalCompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import CompetitorCleanedRow, CompetitorUploadStatus
from apps.api.app.services.competitor_verification import CompetitorVerificationService


def test_manual_evidence_verifies_at_three_distinct_competitor_matches() -> None:
    repository, workspace_id, upload_id = _repository_with_rows(["coffee beans"])
    service = CompetitorVerificationService(repository=repository)

    result = service.verify(
        workspace_id=workspace_id,
        upload_id=upload_id,
        competitors=["Competitor A", "Competitor B", "Competitor C"],
        evidence_rows=[
            {
                "search_term": "coffee beans",
                "results": [
                    {"position": 1, "matched_competitor_name": "Competitor A"},
                    {"position": 4, "matched_competitor_name": "Competitor B"},
                    {"position": 15, "matched_competitor_name": "Competitor C"},
                ],
            }
        ],
    )

    assert result.verified_count == 1
    assert result.preview_rows[0].verification_status == "verified"
    assert result.preview_rows[0].verification_result_json["competitor_matches_found"] == 3
    assert result.preview_rows[0].verification_result_json["verification_method"] == "manual_evidence"


def test_manual_evidence_rejects_below_threshold_and_ignores_unknown_competitors() -> None:
    repository, workspace_id, upload_id = _repository_with_rows(["coffee beans"])
    service = CompetitorVerificationService(repository=repository)

    result = service.verify(
        workspace_id=workspace_id,
        upload_id=upload_id,
        competitors=["Competitor A", "Competitor B", "Competitor C"],
        evidence_rows=[
            {
                "search_term": "coffee beans",
                "results": [
                    {"position": 1, "matched_competitor_name": "Competitor A"},
                    {"position": 2, "matched_competitor_name": "Unknown Competitor"},
                ],
            }
        ],
    )

    assert result.verified_count == 0
    assert result.unverified_count == 1
    assert result.preview_rows[0].verification_status == "unverified"
    assert result.preview_rows[0].verification_result_json["competitor_matches_found"] == 1


def test_manual_evidence_checks_only_top_15_results() -> None:
    repository, workspace_id, upload_id = _repository_with_rows(["coffee beans"])
    service = CompetitorVerificationService(repository=repository)

    result = service.verify(
        workspace_id=workspace_id,
        upload_id=upload_id,
        competitors=["Competitor A", "Competitor B", "Competitor C"],
        evidence_rows=[
            {
                "search_term": "coffee beans",
                "results": [
                    {"position": 1, "matched_competitor_name": "Competitor A"},
                    {"position": 2, "matched_competitor_name": "Competitor B"},
                    {"position": 16, "matched_competitor_name": "Competitor C"},
                ],
            }
        ],
    )

    assert result.preview_rows[0].verification_status == "unverified"
    assert result.preview_rows[0].verification_result_json["competitor_matches_found"] == 2


def _repository_with_rows(search_terms: list[str]):
    workspace_id = uuid4()
    upload_id = uuid4()
    repository = LocalCompetitorCleanedRepository()
    repository.create_upload(
        upload_id=upload_id,
        workspace_id=workspace_id,
        product_id=None,
        original_filename="competitors.csv",
        storage_path="uploads/competitors.csv",
        mime_type="text/csv",
        file_size_bytes=100,
        uploaded_by=str(uuid4()),
    )
    repository.update_upload_status(workspace_id=workspace_id, upload_id=upload_id, status=CompetitorUploadStatus.SUCCEEDED)
    now = datetime.now(UTC)
    repository.insert_rows(rows=[
        CompetitorCleanedRow(
            id=uuid4(),
            workspace_id=workspace_id,
            competitor_upload_id=upload_id,
            row_number=index,
            search_term=term,
            search_volume=1000,
            competitor_rank_values_json=[{"numeric_value": "1"} for _ in range(3)],
            relevance_score=3,
            scoring_status="approved",
            created_at=now,
        )
        for index, term in enumerate(search_terms, start=1)
    ])
    return repository, workspace_id, upload_id
