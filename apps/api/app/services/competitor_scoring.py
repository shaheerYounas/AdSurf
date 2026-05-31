from dataclasses import dataclass
from datetime import UTC, datetime
import json
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.competitor_cleaned import CompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import (
    CompetitorCleanedRow,
    CompetitorScoringResponse,
    CompetitorUpload,
)
from apps.api.app.services.dual_path_decision import DualPathDecisionService, safety_prompt_snippet

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


# =============================================================================
# Dual-Path Competitor Scoring: Deterministic + AI
# =============================================================================

COMPETITOR_SCORING_AI_AGENT_ID = "competitor_scoring_agent"


class DualPathCompetitorScoring(DualPathDecisionService[list[dict]]):
    """Dual-path competitor scoring service.

    Deterministic path: _score_batch (exact rank-count threshold scoring).
    AI path: LLM reviews competitor rows and assigns relevance scores.
    Both paths produce the same output schema (list of scored dicts).
    """

    AGENT_ID = COMPETITOR_SCORING_AI_AGENT_ID
    AGENT_DISPLAY_NAME = "Competitor Scoring Agent"

    def _deterministic_path(self, inputs: dict) -> list[dict]:
        """Run deterministic competitor scoring on rows."""
        rows: list[CompetitorCleanedRow] = inputs["rows"]
        scored: list[dict] = []
        for row in rows:
            rank_values = row.competitor_rank_values_json or []
            if not rank_values:
                scored.append(_scored_row_dict(row, status="error", reason="no_rank_columns_found"))
                continue
            if not row.search_term:
                scored.append(_scored_row_dict(row, status="error", reason="missing_search_term"))
                continue
            relevance = sum(1 for rv in rank_values[:10] if _parse_float(rv.get("numeric_value")) is not None and _parse_float(rv.get("numeric_value")) > 0 and _parse_float(rv.get("numeric_value")) < 15)  # type: ignore[arg-type]
            if relevance >= 3:
                scored.append(_scored_row_dict(row, relevance_score=relevance, status="approved"))
            else:
                scored.append(_scored_row_dict(row, relevance_score=relevance, status="rejected", reason=f"relevance_score_{relevance}_below_threshold"))
        return scored

    def _ai_prompt(self, inputs: dict) -> list[dict[str, str]]:
        rows: list[CompetitorCleanedRow] = inputs["rows"]
        rows_for_prompt = _serialize_competitor_rows_for_ai(rows[:200])

        system = (
            "You are the AdSurf Competitor Scoring Agent for Amazon competitor keyword analysis. "
            "Your job is to review competitor keyword rows and assign relevance scores. "
            f"{safety_prompt_snippet()}"
            "Return JSON only. Do not recalculate metrics. "
            "Every output must include decision_source='ai' and approval_required=true."
        )
        user = {
            "task": "score_competitor_rows",
            "rows": rows_for_prompt,
            "scoring_rules": {
                "relevance_threshold": 3,
                "approve_if_relevance_gte_3": True,
                "reject_if_relevance_lt_3": True,
                "rank_under_15_counts_for_relevance": True,
                "error_conditions": ["no_rank_columns_found", "missing_search_term"],
            },
            "required_output_shape": {
                "candidates": [
                    {
                        "search_term": "string",
                        "search_volume": "number or null",
                        "relevance_score": "integer (0-10)",
                        "scoring_status": "approved | rejected | error",
                        "rejection_reason": "string or null",
                        "ai_confidence": "high | medium | low",
                        "ai_reasoning": "brief explanation",
                        "decision_source": "ai",
                        "requires_human_approval": True,
                        "executes_live_amazon_change": False,
                    }
                ]
            },
        }
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, default=str, sort_keys=True)},
        ]

    def _validate_ai_output(self, ai_json: dict, inputs: dict) -> list[str]:
        errors: list[str] = []
        candidates = ai_json.get("candidates", [])
        if not candidates:
            errors.append("AI output must include at least one candidate.")
        for i, candidate in enumerate(candidates):
            prefix = f"candidates[{i}]"
            status = candidate.get("scoring_status")
            if status not in ("approved", "rejected", "error"):
                errors.append(f"{prefix}.scoring_status must be 'approved', 'rejected', or 'error'.")
            if candidate.get("decision_source") != "ai":
                errors.append(f"{prefix}.decision_source must be 'ai'.")
            if candidate.get("requires_human_approval") is not True:
                errors.append(f"{prefix}.requires_human_approval must be true.")
            if candidate.get("executes_live_amazon_change") is not False:
                errors.append(f"{prefix}.executes_live_amazon_change must be false.")
        return errors

    def _parse_ai_output(self, ai_json: dict, inputs: dict) -> list[dict]:
        candidates = ai_json.get("candidates", [])
        parsed: list[dict] = []
        for candidate in candidates:
            parsed.append({
                "search_term": candidate.get("search_term"),
                "search_volume": candidate.get("search_volume"),
                "relevance_score": int(candidate.get("relevance_score", 0)),
                "scoring_status": candidate.get("scoring_status", "error"),
                "rejection_reason": candidate.get("rejection_reason"),
                "ai_confidence": candidate.get("ai_confidence", "medium"),
                "ai_reasoning": candidate.get("ai_reasoning", ""),
                "decision_source": "ai",
            })
        return parsed

    def _empty_result(self) -> list[dict]:
        return []


def _scored_row_dict(row: CompetitorCleanedRow, *, relevance_score: int = 0, status: str = "error", reason: str | None = None) -> dict:
    return {
        "row_id": str(row.id) if row.id else None,
        "search_term": row.search_term,
        "search_volume": str(row.search_volume) if row.search_volume else None,
        "relevance_score": relevance_score,
        "scoring_status": status,
        "rejection_reason": reason,
        "decision_source": "deterministic",
    }


def _serialize_competitor_rows_for_ai(rows: list[CompetitorCleanedRow]) -> list[dict]:
    serialized: list[dict] = []
    for row in rows:
        rank_values = row.competitor_rank_values_json or []
        serialized.append({
            "search_term": row.search_term,
            "search_volume": str(row.search_volume) if row.search_volume else None,
            "competitor_rank_values": [{
                "column_name": rv.get("column_name"),
                "numeric_value": rv.get("numeric_value"),
            } for rv in rank_values],
        })
    return serialized
