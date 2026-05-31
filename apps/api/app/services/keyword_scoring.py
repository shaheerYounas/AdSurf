from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
from uuid import UUID, uuid4

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.column_mapping import ColumnMappingRepository
from apps.api.app.repositories.keyword_scoring import KeywordScoringRepository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository
from apps.api.app.schemas.agent_control import AgentMode
from apps.api.app.schemas.column_mapping import ColumnMapping, ColumnMappingStatus
from apps.api.app.schemas.keyword_scoring import KeywordCandidate, KeywordCandidateStatus, KeywordScoringRun
from apps.api.app.schemas.upload_parsing import ParsedUploadRow
from apps.api.app.services.dual_path_decision import DualPathDecisionService, DualPathResult, safety_prompt_snippet


SCORING_ROWS_PAGE_SIZE = 500


@dataclass(frozen=True)
class KeywordScoringResult:
    run: KeywordScoringRun
    created: bool


class KeywordScoringFailedError(Exception):
    def __init__(self, *, run: KeywordScoringRun, message: str) -> None:
        super().__init__(message)
        self.run = run
        self.message = message


class KeywordScoringService:
    def __init__(
        self,
        *,
        column_repository: ColumnMappingRepository,
        parsing_repository: UploadParsingRepository,
        scoring_repository: KeywordScoringRepository,
    ) -> None:
        self._column_repository = column_repository
        self._parsing_repository = parsing_repository
        self._scoring_repository = scoring_repository

    def score_mapping(self, *, workspace_id: UUID, mapping_id: UUID, idempotency_key: str) -> KeywordScoringResult:
        existing = self._scoring_repository.get_run_by_idempotency_key(workspace_id=workspace_id, idempotency_key=idempotency_key)
        if existing is not None:
            if existing.column_mapping_id != mapping_id:
                raise ApiError(
                    code="IDEMPOTENCY_KEY_CONFLICT",
                    message="Idempotency-Key was already used for a different keyword scoring request.",
                    status_code=409,
                )
            return KeywordScoringResult(run=existing, created=False)

        mapping = self._column_repository.get_mapping(workspace_id=workspace_id, mapping_id=mapping_id)
        if mapping is None:
            raise ApiError(code="COLUMN_MAPPING_NOT_FOUND", message="Column mapping was not found.", status_code=404)
        if mapping.status != ColumnMappingStatus.APPROVED:
            raise ApiError(code="COLUMN_MAPPING_NOT_APPROVED", message="Only approved column mappings can be scored.", status_code=409)

        run = self._scoring_repository.create_run(mapping=mapping, idempotency_key=idempotency_key)
        try:
            rows = self._load_rows(mapping)
            candidates = [_score_row(mapping=mapping, row=row) for row in rows]
            completed = self._scoring_repository.complete_run(run=run, candidates=candidates)
            return KeywordScoringResult(run=completed, created=True)
        except Exception as exc:
            failed_run = self._scoring_repository.fail_run(run=run, error_message=str(exc))
            raise KeywordScoringFailedError(run=failed_run, message=str(exc)) from exc

    def _load_rows(self, mapping: ColumnMapping) -> list[ParsedUploadRow]:
        rows: list[ParsedUploadRow] = []
        page = 1
        while True:
            page_rows, total = self._parsing_repository.list_rows(
                workspace_id=mapping.workspace_id,
                parse_run_id=mapping.parse_run_id,
                page=page,
                page_size=SCORING_ROWS_PAGE_SIZE,
            )
            rows.extend(page_rows)
            if page * SCORING_ROWS_PAGE_SIZE >= total:
                return rows
            page += 1


def _score_row(*, mapping: ColumnMapping, row: ParsedUploadRow) -> KeywordCandidate:
    now = datetime.now(UTC)
    row_data = row.row_data_json or {}
    if _is_empty_row(row_data):
        return _candidate(
            mapping=mapping,
            row=row,
            now=now,
            search_term=None,
            search_volume=None,
            rank_values=[],
            relevance_score=None,
            status=KeywordCandidateStatus.ERROR,
            reason="empty_row",
        )

    search_term = _string_value(_row_value(row_data, mapping.mapping_json["search_term"]))
    if not search_term:
        return _candidate(
            mapping=mapping,
            row=row,
            now=now,
            search_term=None,
            search_volume=None,
            rank_values=[],
            relevance_score=None,
            status=KeywordCandidateStatus.ERROR,
            reason="missing_search_term",
        )

    search_volume_raw = _row_value(row_data, mapping.mapping_json["search_volume"])
    search_volume = _parse_decimal(search_volume_raw)
    if search_volume is None or search_volume < 0:
        return _candidate(
            mapping=mapping,
            row=row,
            now=now,
            search_term=search_term,
            search_volume=None,
            rank_values=[],
            relevance_score=None,
            status=KeywordCandidateStatus.ERROR,
            reason="invalid_search_volume",
        )

    rank_values = []
    impossible_rank = False
    relevance_score = 0
    for column_reference in mapping.mapping_json["competitor_rank_columns"]:
        raw_value = _row_value(row_data, column_reference)
        rank = _parse_decimal(raw_value)
        payload = {
            "column_name": column_reference["original_column_name"],
            "raw_value": raw_value,
            "numeric_value": str(rank) if rank is not None else None,
            "counts_for_relevance": False,
            "warning": None,
            "error": None,
        }
        if _is_blank(raw_value):
            payload["warning"] = "blank_rank_not_counted"
        elif rank is None:
            payload["warning"] = "non_numeric_rank_not_counted"
        elif rank <= 0:
            payload["error"] = "invalid_competitor_rank"
            impossible_rank = True
        elif rank < 15:
            payload["counts_for_relevance"] = True
            relevance_score += 1
        rank_values.append(payload)

    if impossible_rank:
        return _candidate(
            mapping=mapping,
            row=row,
            now=now,
            search_term=search_term,
            search_volume=search_volume,
            rank_values=rank_values,
            relevance_score=None,
            status=KeywordCandidateStatus.ERROR,
            reason="invalid_competitor_rank",
        )

    status = KeywordCandidateStatus.APPROVED if relevance_score >= 3 else KeywordCandidateStatus.REJECTED
    reason = None if status == KeywordCandidateStatus.APPROVED else f"relevance_score_{relevance_score}_below_threshold"
    return _candidate(
        mapping=mapping,
        row=row,
        now=now,
        search_term=search_term,
        search_volume=search_volume,
        rank_values=rank_values,
        relevance_score=relevance_score,
        status=status,
        reason=reason,
    )


def _candidate(
    *,
    mapping: ColumnMapping,
    row: ParsedUploadRow,
    now: datetime,
    search_term: str | None,
    search_volume: Decimal | None,
    rank_values: list[dict],
    relevance_score: int | None,
    status: KeywordCandidateStatus,
    reason: str | None,
) -> KeywordCandidate:
    return KeywordCandidate(
        id=uuid4(),
        workspace_id=mapping.workspace_id,
        product_id=mapping.product_id,
        upload_id=mapping.upload_id,
        parse_run_id=mapping.parse_run_id,
        column_mapping_id=mapping.id,
        scoring_run_id=uuid4(),
        source_row_id=row.id or uuid4(),
        search_term=search_term,
        search_volume=search_volume,
        competitor_rank_values_json=rank_values,
        relevance_score=relevance_score,
        scoring_status=status,
        rejection_reason=reason,
        created_at=now,
        updated_at=now,
    )


def _row_value(row_data: dict, column_reference: dict | None):
    if column_reference is None:
        return None
    return row_data.get(column_reference["original_column_name"])


def _string_value(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_decimal(value) -> Decimal | None:
    if isinstance(value, bool) or _is_blank(value):
        return None
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_empty_row(row_data: dict) -> bool:
    return not row_data or all(_is_blank(value) for value in row_data.values())


# =============================================================================
# Dual-Path Keyword Scoring: Deterministic + AI
# =============================================================================

KEYWORD_SCORING_AI_AGENT_ID = "keyword_scoring_agent"
KEYWORD_SCORING_AI_SCHEMA_VERSION = "keyword_scoring_ai_v1"


class DualPathKeywordScoring(DualPathDecisionService[list[dict]]):
    """Dual-path keyword scoring service.

    Deterministic path: _score_row (exact rule-based scoring).
    AI path: LLM reviews rows and assigns scores with explanations.
    Both paths produce the same output schema (list of candidate dicts).
    """

    AGENT_ID = KEYWORD_SCORING_AI_AGENT_ID
    AGENT_DISPLAY_NAME = "Keyword Scoring Agent"

    def _deterministic_path(self, inputs: dict) -> list[dict]:
        """Run deterministic scoring on rows."""
        mapping: ColumnMapping = inputs["mapping"]
        rows: list[ParsedUploadRow] = inputs["rows"]
        return [_score_row_candidate_dict(mapping=mapping, row=row) for row in rows]

    def _ai_prompt(self, inputs: dict) -> list[dict[str, str]]:
        mapping: ColumnMapping = inputs["mapping"]
        rows: list[ParsedUploadRow] = inputs["rows"]
        rows_for_prompt = _serialize_rows_for_ai(rows[:200], mapping)  # Limit to 200 rows per AI call

        system = (
            "You are the AdSurf Keyword Scoring Agent for Amazon competitor keyword analysis. "
            "Your job is to review parsed competitor keyword rows and assign scores. "
            f"{safety_prompt_snippet()}"
            "Return JSON only. Do not recalculate metrics that are already provided. "
            "Every output must include decision_source='ai' and approval_required=true."
        )
        user = {
            "task": "score_keyword_rows",
            "mapping": {
                "search_term_column": mapping.mapping_json.get("search_term", {}).get("original_column_name") if mapping.mapping_json.get("search_term") else None,
                "search_volume_column": mapping.mapping_json.get("search_volume", {}).get("original_column_name") if mapping.mapping_json.get("search_volume") else None,
                "competitor_rank_columns": [
                    col.get("original_column_name") for col in mapping.mapping_json.get("competitor_rank_columns", [])
                ],
            },
            "rows": rows_for_prompt,
            "scoring_rules": {
                "relevance_threshold": 3,
                "approve_if_relevance_gte_3": True,
                "reject_if_relevance_lt_3": True,
                "error_conditions": ["missing_search_term", "invalid_search_volume", "empty_row", "invalid_competitor_rank"],
            },
            "required_output_shape": {
                "candidates": [
                    {
                        "search_term": "string or null",
                        "search_volume": "number or null",
                        "relevance_score": "integer (0-10)",
                        "scoring_status": "approved | rejected | error",
                        "rejection_reason": "string or null",
                        "rank_columns_evaluated": ["list of column names with counts_for_relevance"],
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
                errors.append(f"{prefix}.scoring_status must be 'approved', 'rejected', or 'error', got '{status}'.")
            if candidate.get("decision_source") != "ai":
                errors.append(f"{prefix}.decision_source must be 'ai'.")
            if candidate.get("requires_human_approval") is not True:
                errors.append(f"{prefix}.requires_human_approval must be true.")
            if candidate.get("executes_live_amazon_change") is not False:
                errors.append(f"{prefix}.executes_live_amazon_change must be false.")
        return errors

    def _parse_ai_output(self, ai_json: dict, inputs: dict) -> list[dict]:
        """Parse AI output into candidate dicts (compatible with deterministic format)."""
        mapping: ColumnMapping = inputs["mapping"]
        rows: list[ParsedUploadRow] = inputs["rows"]
        candidates = ai_json.get("candidates", [])
        parsed: list[dict] = []
        for i, ai_candidate in enumerate(candidates):
            row = rows[i] if i < len(rows) else None
            parsed.append({
                "search_term": ai_candidate.get("search_term"),
                "search_volume": Decimal(str(ai_candidate.get("search_volume", 0))) if ai_candidate.get("search_volume") is not None else None,
                "relevance_score": int(ai_candidate.get("relevance_score", 0)),
                "scoring_status": ai_candidate.get("scoring_status", "error"),
                "rejection_reason": ai_candidate.get("rejection_reason"),
                "rank_values": ai_candidate.get("rank_columns_evaluated", []),
                "ai_confidence": ai_candidate.get("ai_confidence", "medium"),
                "ai_reasoning": ai_candidate.get("ai_reasoning", ""),
                "decision_source": "ai",
                "source_row_id": str(row.id) if row and row.id else None,
            })
        return parsed

    def _empty_result(self) -> list[dict]:
        return []


def _score_row_candidate_dict(*, mapping: ColumnMapping, row: ParsedUploadRow) -> dict:
    """Score a row and return as a plain dict (for dual-path output)."""
    candidate = _score_row(mapping=mapping, row=row)
    return {
        "search_term": candidate.search_term,
        "search_volume": candidate.search_volume,
        "relevance_score": candidate.relevance_score,
        "scoring_status": candidate.scoring_status.value,
        "rejection_reason": candidate.rejection_reason,
        "rank_values": candidate.competitor_rank_values_json,
        "decision_source": "deterministic",
        "source_row_id": str(candidate.source_row_id),
    }


def _serialize_rows_for_ai(rows: list[ParsedUploadRow], mapping: ColumnMapping) -> list[dict]:
    """Serialize parsed upload rows into AI-friendly format."""
    serialized: list[dict] = []
    search_term_key = mapping.mapping_json.get("search_term", {}).get("original_column_name", "")
    search_volume_key = mapping.mapping_json.get("search_volume", {}).get("original_column_name", "")
    rank_keys = [col.get("original_column_name", "") for col in mapping.mapping_json.get("competitor_rank_columns", [])]
    for row in rows:
        data = row.row_data_json or {}
        serialized.append({
            "row_number": row.row_number,
            "search_term": _string_value(data.get(search_term_key)),
            "search_volume": _string_value(data.get(search_volume_key)),
            "competitor_rank_values": {key: _string_value(data.get(key)) for key in rank_keys if key},
        })
    return serialized
