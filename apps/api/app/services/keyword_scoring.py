from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.column_mapping import ColumnMappingRepository
from apps.api.app.repositories.keyword_scoring import KeywordScoringRepository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository
from apps.api.app.schemas.column_mapping import ColumnMapping, ColumnMappingStatus
from apps.api.app.schemas.keyword_scoring import KeywordCandidate, KeywordCandidateStatus, KeywordScoringRun
from apps.api.app.schemas.upload_parsing import ParsedUploadRow


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
