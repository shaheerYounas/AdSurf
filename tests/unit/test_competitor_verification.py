from datetime import UTC, datetime
from uuid import uuid4

from apps.api.app.repositories.competitor_cleaned import LocalCompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import CompetitorCleanedRow, CompetitorUploadStatus
from apps.api.app.services.amazon_search_agent import AmazonSearchAgentOptions, AmazonSearchEvidenceAgent, AmazonSearchEvidenceProvider
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


def test_manual_amazon_search_text_auto_matches_competitor_names() -> None:
    repository, workspace_id, upload_id = _repository_with_rows(["coffee beans"])
    service = CompetitorVerificationService(repository=repository)

    result = service.verify(
        workspace_id=workspace_id,
        upload_id=upload_id,
        competitors=["Acme Coffee", "Bean Lab", "Roast House"],
        evidence_text_rows=[
            {
                "search_term": "coffee beans",
                "pasted_results": "\n".join([
                    "1. Acme Coffee organic whole beans B0ACME1111",
                    "2. Bean Lab medium roast B0BEAN2222",
                    "3. Other brand result B0OTHER333",
                    "4. Roast House espresso beans B0ROAST444",
                ]),
            }
        ],
        verification_method="manual_amazon_search",
    )

    assert result.verified_count == 1
    evidence = result.preview_rows[0].verification_result_json
    assert evidence["verification_method"] == "manual_amazon_search"
    assert evidence["competitor_matches_found"] == 3
    assert {match["match_source"] for match in evidence["matched_competitors"]} == {"result_title_name"}


def test_manual_amazon_search_text_auto_matches_competitor_asins() -> None:
    repository, workspace_id, upload_id = _repository_with_rows(["coffee beans"])
    service = CompetitorVerificationService(repository=repository)

    result = service.verify(
        workspace_id=workspace_id,
        upload_id=upload_id,
        competitors=[
            {"name": "Acme Coffee", "asin": "B0ACME1111"},
            {"name": "Bean Lab", "asin": "B0BEAN2222"},
            {"name": "Roast House", "asin": "B0ROAST444"},
        ],
        evidence_text_rows=[
            {
                "search_term": "coffee beans",
                "pasted_results": "\n".join([
                    "1. Premium whole beans B0ACME1111",
                    "2. Medium roast B0BEAN2222",
                    "3. Espresso beans B0ROAST444",
                ]),
            }
        ],
        verification_method="manual_amazon_search",
    )

    assert result.preview_rows[0].verification_status == "verified"
    evidence = result.preview_rows[0].verification_result_json
    assert evidence["competitor_matches_found"] == 3
    assert {match["match_source"] for match in evidence["matched_competitors"]} == {"result_asin"}


def test_agentic_browser_verification_uses_collected_amazon_evidence() -> None:
    repository, workspace_id, upload_id = _repository_with_rows(["coffee beans"])
    service = CompetitorVerificationService(repository=repository)

    result, evidence_rows = service.verify_with_browser_agent(
        workspace_id=workspace_id,
        upload_id=upload_id,
        competitors=["Acme Coffee", "Bean Lab", "Roast House"],
        search_agent=AmazonSearchEvidenceAgent(provider=_FakeAmazonProvider()),
    )

    assert len(evidence_rows) == 1
    assert result.verified_count == 1
    evidence = result.preview_rows[0].verification_result_json
    assert evidence["verification_method"] == "agentic_browser_search"
    assert evidence["competitor_matches_found"] == 3
    assert {match["match_source"] for match in evidence["matched_competitors"]} == {"result_title_name"}


class _FakeAmazonProvider(AmazonSearchEvidenceProvider):
    def search(self, *, search_term: str, options: AmazonSearchAgentOptions):
        return {
            "search_term": search_term,
            "results": [
                {"position": 1, "title": "Acme Coffee organic whole beans", "asin": "B0ACME1111"},
                {"position": 2, "title": "Bean Lab medium roast", "asin": "B0BEAN2222"},
                {"position": 3, "title": "Roast House espresso beans", "asin": "B0ROAST444"},
            ],
        }


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
