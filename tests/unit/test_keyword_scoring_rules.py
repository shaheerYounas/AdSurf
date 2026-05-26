from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from apps.api.app.schemas.column_mapping import ColumnMapping, ColumnMappingStatus, ColumnMappingType
from apps.api.app.schemas.keyword_scoring import KeywordCandidateStatus
from apps.api.app.schemas.upload_parsing import ParsedUploadRow
from apps.api.app.services.keyword_scoring import _score_row


def test_relevance_score_counts_ranks_under_15_and_excludes_15() -> None:
    candidate = _score_row(mapping=_mapping(), row=_row({"Search Term": "shoes", "Search Volume": "100", "Rank 1": "1", "Rank 2": "14", "Rank 3": "15"}))

    assert candidate.relevance_score == 2
    assert candidate.scoring_status == KeywordCandidateStatus.REJECTED
    assert candidate.rejection_reason == "relevance_score_2_below_threshold"


def test_score_three_or_more_is_approved() -> None:
    candidate = _score_row(mapping=_mapping(), row=_row({"Search Term": "shoes", "Search Volume": "100", "Rank 1": "1", "Rank 2": "2", "Rank 3": "3"}))

    assert candidate.relevance_score == 3
    assert candidate.scoring_status == KeywordCandidateStatus.APPROVED
    assert candidate.rejection_reason is None


def test_blank_and_non_numeric_ranks_do_not_count_with_deterministic_warning() -> None:
    candidate = _score_row(mapping=_mapping(), row=_row({"Search Term": "shoes", "Search Volume": "100", "Rank 1": "", "Rank 2": "n/a", "Rank 3": "8"}))

    assert candidate.relevance_score == 1
    assert candidate.scoring_status == KeywordCandidateStatus.REJECTED
    assert [rank["warning"] for rank in candidate.competitor_rank_values_json[:2]] == ["blank_rank_not_counted", "non_numeric_rank_not_counted"]


def test_blank_search_term_is_row_error() -> None:
    candidate = _score_row(mapping=_mapping(), row=_row({"Search Term": " ", "Search Volume": "100", "Rank 1": "1", "Rank 2": "2", "Rank 3": "3"}))

    assert candidate.scoring_status == KeywordCandidateStatus.ERROR
    assert candidate.rejection_reason == "missing_search_term"


def test_negative_search_volume_is_row_error() -> None:
    candidate = _score_row(mapping=_mapping(), row=_row({"Search Term": "shoes", "Search Volume": "-1", "Rank 1": "1", "Rank 2": "2", "Rank 3": "3"}))

    assert candidate.scoring_status == KeywordCandidateStatus.ERROR
    assert candidate.rejection_reason == "invalid_search_volume"


def test_impossible_rank_is_row_error() -> None:
    candidate = _score_row(mapping=_mapping(), row=_row({"Search Term": "shoes", "Search Volume": "100", "Rank 1": "0", "Rank 2": "2", "Rank 3": "3"}))

    assert candidate.scoring_status == KeywordCandidateStatus.ERROR
    assert candidate.rejection_reason == "invalid_competitor_rank"


def _mapping() -> ColumnMapping:
    now = datetime.now(UTC)
    return ColumnMapping(
        id=uuid4(),
        workspace_id=uuid4(),
        product_id=uuid4(),
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        column_profile_id=uuid4(),
        status=ColumnMappingStatus.APPROVED,
        mapping_version=1,
        mapping_type=ColumnMappingType.MANUAL,
        mapping_json={
            "search_term": {"column_id": str(uuid4()), "original_column_name": "Search Term", "normalized_column_name": "search term"},
            "search_volume": {"column_id": str(uuid4()), "original_column_name": "Search Volume", "normalized_column_name": "search volume"},
            "competitor_rank_columns": [
                {"column_id": str(uuid4()), "original_column_name": "Rank 1", "normalized_column_name": "rank 1"},
                {"column_id": str(uuid4()), "original_column_name": "Rank 2", "normalized_column_name": "rank 2"},
                {"column_id": str(uuid4()), "original_column_name": "Rank 3", "normalized_column_name": "rank 3"},
            ],
        },
        validation_errors_json=[],
        created_by=uuid4(),
        created_at=now,
        approved_at=now,
    )


def _row(row_data: dict) -> ParsedUploadRow:
    return ParsedUploadRow(id=uuid4(), row_number=1, row_data_json=row_data, row_hash=str(uuid4()))
