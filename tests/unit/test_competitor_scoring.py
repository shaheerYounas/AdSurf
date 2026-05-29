"""Tests for the relevance scoring engine defined in the marketing plan.

Validates:
- rank < 15 rule
- top 10 competitors limit (Bug 4 fix)
- score range 0 to 10
- scores 0, 1, 2 filtered out
- evidence saved per term
"""

from apps.api.app.services.competitor_scoring import _parse_float

# We can test _score_batch independently using the CompetitorCleanedRow pydantic model
import pytest


@pytest.fixture
def make_row():
    """Factory fixture to create clean row dicts for _score_batch testing."""
    from uuid import uuid4
    from datetime import UTC, datetime
    from apps.api.app.schemas.competitor_cleaned import CompetitorCleanedRow

    def _make(
        search_term: str = "test term",
        rank_values: list[dict] | None = None,
    ) -> CompetitorCleanedRow:
        return CompetitorCleanedRow(
            id=uuid4(),
            workspace_id=uuid4(),
            competitor_upload_id=uuid4(),
            row_number=1,
            search_term=search_term,
            search_volume=1000,
            competitor_rank_values_json=rank_values or [],
            created_at=datetime.now(UTC),
        )

    return _make


# ── parse_float helpers ────────────────────────────────────────────────────

def test_parse_float_returns_none_for_empty() -> None:
    assert _parse_float(None) is None
    assert _parse_float("") is None


def test_parse_float_handles_integer() -> None:
    assert _parse_float("5") == 5.0
    assert _parse_float(14) == 14.0


def test_parse_float_handles_comma() -> None:
    assert _parse_float("1,000") == 1000.0


def test_parse_float_returns_none_on_invalid() -> None:
    assert _parse_float("abc") is None
    assert _parse_float("N/A") is None


# ── Relevance scoring logic ─────────────────────────────────────────────────

def test_all_ten_competitors_below_15_gives_score_10(make_row) -> None:
    """10 competitors all rank < 15 gives score 10."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="very relevant",
        rank_values=[
            {"competitor": f"Comp{i}", "numeric_value": i + 1}
            for i in range(10)
        ],
    )
    result = _score_batch([row])
    assert result.approved_count == 1
    assert result.rows[0].relevance_score == 10
    assert result.rows[0].scoring_status == "approved"


def test_five_competitors_below_15_gives_score_5(make_row) -> None:
    """5 out of 10 competitors rank < 15 gives score 5."""
    from apps.api.app.services.competitor_scoring import _score_batch

    rank_values = []
    for i in range(10):
        rank_values.append({"competitor": f"Comp{i}", "numeric_value": i + 1 if i < 5 else i + 20})
    row = make_row(search_term="moderate", rank_values=rank_values)
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 5
    assert result.rows[0].scoring_status == "approved"


def test_zero_competitors_below_15_gives_score_0(make_row) -> None:
    """0 competitors rank < 15 gives score 0."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="irrelevant",
        rank_values=[
            {"competitor": f"Comp{i}", "numeric_value": i + 20}
            for i in range(10)
        ],
    )
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 0
    assert result.rows[0].scoring_status == "rejected"
    assert "relevance_score_0" in str(result.rows[0].rejection_reason)


def test_score_0_is_rejected(make_row) -> None:
    """Score 0 should be rejected (no competitors rank < 15)."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="score0",
        rank_values=[{"competitor": "Comp0", "numeric_value": 20}],
    )
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 0
    assert result.rows[0].scoring_status == "rejected"


def test_score_1_is_rejected(make_row) -> None:
    """Score 1 should be rejected."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="score1",
        rank_values=[{"competitor": "Comp0", "numeric_value": 5}],
    )
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 1
    assert result.rows[0].scoring_status == "rejected"


def test_score_2_is_rejected(make_row) -> None:
    """Score 2 should be rejected."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="score2",
        rank_values=[
            {"competitor": "Comp0", "numeric_value": 1},
            {"competitor": "Comp1", "numeric_value": 2},
        ],
    )
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 2
    assert result.rows[0].scoring_status == "rejected"


def test_score_3_is_approved(make_row) -> None:
    """Score >= 3 should be approved."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="barely approved",
        rank_values=[{"competitor": f"Comp{i}", "numeric_value": 1} for i in range(3)],
    )
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 3
    assert result.rows[0].scoring_status == "approved"


def test_rank_exactly_14_counts(make_row) -> None:
    """rank < 15 means rank 14 counts."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="rank14",
        rank_values=[{"competitor": "Comp0", "numeric_value": 14}],
    )
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 1


def test_rank_exactly_15_does_not_count(make_row) -> None:
    """rank = 15 does NOT count (must be < 15)."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="rank15",
        rank_values=[{"competitor": "Comp0", "numeric_value": 15}],
    )
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 0


def test_rank_zero_or_negative_does_not_count(make_row) -> None:
    """rank <= 0 doesn't count."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="zero",
        rank_values=[
            {"competitor": "Comp0", "numeric_value": 0},
            {"competitor": "Comp1", "numeric_value": -1},
        ],
    )
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 0


def test_counts_only_top_10_competitors(make_row) -> None:
    """Bug 4 fix: Only first 10 rank values are counted, not all."""
    from apps.api.app.services.competitor_scoring import _score_batch

    # 15 competitors all rank 1 (< 15), but only top 10 should count
    rank_values = [{"competitor": f"Comp{i}", "numeric_value": 1} for i in range(15)]
    row = make_row(search_term="fifteen competitors", rank_values=rank_values)
    result = _score_batch([row])
    assert result.rows[0].relevance_score == 10  # capped at 10
    assert result.rows[0].scoring_status == "approved"


def test_missing_search_term_is_error(make_row) -> None:
    """Row with empty search term should be marked as error."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(
        search_term="",
        rank_values=[{"competitor": "Comp0", "numeric_value": 1}],
    )
    result = _score_batch([row])
    assert result.error_count == 1
    assert result.rows[0].scoring_status == "error"
    assert "missing_search_term" in str(result.rows[0].rejection_reason)


def test_no_rank_values_is_error(make_row) -> None:
    """Row with empty competitor_rank_values_json is an error."""
    from apps.api.app.services.competitor_scoring import _score_batch

    row = make_row(search_term="test", rank_values=None)
    result = _score_batch([row])
    assert result.error_count == 1
    assert result.rows[0].scoring_status == "error"
    assert "no_rank_columns_found" in str(result.rows[0].rejection_reason)