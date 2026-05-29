from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.competitor_cleaned import CompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import (
    CompetitorCleanedRow,
    CompetitorScoringResponse,
    CompetitorUpload,
)

SCORING_PAGE_SIZE = 1000


@dataclass(frozen=True)
class ScoredBatch:
    rows: list[CompetitorCleanedRow]
    approved_count: int
    rejected_count: int
    error_count: int


class CompetitorScoringService:
    def __init__(self, repository: CompetitorCleanedRepository) -> None:
        self._repository = repository

    def score_upload(self, *, workspace_id: UUID, upload_id: UUID) -> CompetitorScoringResponse:
        upload = self._repository.get_upload(workspace_id=workspace_id, upload_id=upload_id)
        if upload is None:
            raise ApiError(code="COMPETITOR_UPLOAD_NOT_FOUND", message="Competitor upload was not found.", status_code=404)
        if upload.status.value not in ("succeeded",):
            raise ApiError(code="COMPETITOR_UPLOAD_NOT_CLEANED", message="Scoring requires a succeeded cleaned upload.", status_code=409)

        approved_total = 0
        rejected_total = 0
        error_total = 0
        all_scored: list[CompetitorCleanedRow] = []
        page = 1

        while True:
            rows, total = self._repository.list_rows(
                workspace_id=workspace_id,
                competitor_upload_id=upload_id,
                page=page,
                page_size=SCORING_PAGE_SIZE,
            )
            if not rows:
                break

            scored = _score_batch(rows)
            self._repository.update_scored_rows(rows=scored.rows)
            approved_total += scored.approved_count
            rejected_total += scored.rejected_count
            error_total += scored.error_count
            all_scored.extend(scored.rows)
            if page * SCORING_PAGE_SIZE >= total:
                break
            page += 1

        return CompetitorScoringResponse(
            upload=upload,
            total_rows=len(all_scored),
            scored_rows=approved_total + rejected_total,
            approved_count=approved_total,
            rejected_count=rejected_total,
            error_count=error_total,
            preview_rows=all_scored[:20],
        )


def _score_batch(rows: list[CompetitorCleanedRow]) -> ScoredBatch:
    now = datetime.now(UTC)
    approved_count = 0
    rejected_count = 0
    error_count = 0
    scored: list[CompetitorCleanedRow] = []

    for row in rows:
        rank_values = row.competitor_rank_values_json or []
        if not rank_values:
            error_count += 1
            scored.append(row.model_copy(update={
                "relevance_score": None,
                "scoring_status": "error",
                "rejection_reason": "no_rank_columns_found",
                "scored_at": now,
            }))
            continue

        if not row.search_term:
            error_count += 1
            scored.append(row.model_copy(update={
                "relevance_score": None,
                "scoring_status": "error",
                "rejection_reason": "missing_search_term",
                "scored_at": now,
            }))
            continue

        relevance_score = 0
        for rv in rank_values[:10]:
            numeric = _parse_float(rv.get("numeric_value"))
            if numeric is not None and numeric > 0 and numeric < 15:
                relevance_score += 1

        if relevance_score >= 3:
            approved_count += 1
            status = "approved"
            reason = None
        else:
            rejected_count += 1
            status = "rejected"
            reason = f"relevance_score_{relevance_score}_below_threshold"

        scored.append(row.model_copy(update={
            "relevance_score": relevance_score,
            "scoring_status": status,
            "rejection_reason": reason,
            "scored_at": now,
        }))

    return ScoredBatch(
        rows=scored,
        approved_count=approved_count,
        rejected_count=rejected_count,
        error_count=error_count,
    )


def _parse_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip().replace(",", ""))
    except (ValueError, TypeError):
        return None