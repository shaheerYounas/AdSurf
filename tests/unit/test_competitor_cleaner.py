from uuid import uuid4

from apps.api.app.repositories.competitor_cleaned import LocalCompetitorCleanedRepository
from apps.api.app.services.competitor_cleaner import CompetitorCleanerService


def test_cleaner_detects_named_competitor_rank_columns() -> None:
    repository = LocalCompetitorCleanedRepository()
    workspace_id = uuid4()
    upload = repository.create_upload(
        upload_id=uuid4(),
        workspace_id=workspace_id,
        product_id=None,
        original_filename="competitors.csv",
        storage_path="uploads/competitors.csv",
        mime_type="text/csv",
        file_size_bytes=128,
        uploaded_by=str(uuid4()),
    )
    content = (
        "Search Term,Search Volume,Competitor A Rank,Competitor B Rank,Competitor C Rank\n"
        "ceramic planter,1200,1,3,7\n"
    ).encode()

    result = CompetitorCleanerService(repository=repository).process(upload=upload, content=content)

    assert result.rows[0].search_term == "ceramic planter"
    assert result.rows[0].competitor_rank_values_json == [
        {"column_name": "Competitor A Rank", "column_index": 2, "raw_value": "1", "numeric_value": "1"},
        {"column_name": "Competitor B Rank", "column_index": 3, "raw_value": "3", "numeric_value": "3"},
        {"column_name": "Competitor C Rank", "column_index": 4, "raw_value": "7", "numeric_value": "7"},
    ]
    assert {warning["code"] for warning in result.warnings} == set()
