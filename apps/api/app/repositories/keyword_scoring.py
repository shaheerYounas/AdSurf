from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.column_mapping import ColumnMapping
from apps.api.app.schemas.keyword_scoring import (
    KeywordCandidate,
    KeywordCandidateStatus,
    KeywordScoringRun,
    KeywordScoringRunStatus,
)


class KeywordScoringRepository(ABC):
    @abstractmethod
    def get_run_by_idempotency_key(self, *, workspace_id: UUID, idempotency_key: str) -> KeywordScoringRun | None:
        raise NotImplementedError

    @abstractmethod
    def create_run(self, *, mapping: ColumnMapping, idempotency_key: str) -> KeywordScoringRun:
        raise NotImplementedError

    @abstractmethod
    def complete_run(self, *, run: KeywordScoringRun, candidates: list[KeywordCandidate]) -> KeywordScoringRun:
        raise NotImplementedError

    @abstractmethod
    def fail_run(self, *, run: KeywordScoringRun, error_message: str) -> KeywordScoringRun:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, *, workspace_id: UUID, scoring_run_id: UUID) -> KeywordScoringRun | None:
        raise NotImplementedError

    @abstractmethod
    def get_candidate(self, *, workspace_id: UUID, candidate_id: UUID) -> KeywordCandidate | None:
        raise NotImplementedError

    @abstractmethod
    def list_candidates(
        self,
        *,
        workspace_id: UUID,
        scoring_run_id: UUID,
        scoring_status: KeywordCandidateStatus | None,
        min_relevance_score: int | None,
        max_relevance_score: int | None,
        search_term: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[KeywordCandidate], int]:
        raise NotImplementedError


class LocalKeywordScoringRepository(KeywordScoringRepository):
    def __init__(self) -> None:
        self._runs: dict[UUID, KeywordScoringRun] = {}
        self._candidates: dict[UUID, list[KeywordCandidate]] = {}

    def get_run_by_idempotency_key(self, *, workspace_id: UUID, idempotency_key: str) -> KeywordScoringRun | None:
        for run in self._runs.values():
            if run.workspace_id == workspace_id and run.idempotency_key == idempotency_key:
                return run
        return None

    def create_run(self, *, mapping: ColumnMapping, idempotency_key: str) -> KeywordScoringRun:
        now = datetime.now(UTC)
        scoring_version = _next_scoring_version([run for run in self._runs.values() if run.column_mapping_id == mapping.id])
        run = KeywordScoringRun(
            id=uuid4(),
            workspace_id=mapping.workspace_id,
            product_id=mapping.product_id,
            upload_id=mapping.upload_id,
            parse_run_id=mapping.parse_run_id,
            column_mapping_id=mapping.id,
            status=KeywordScoringRunStatus.RUNNING,
            scoring_version=scoring_version,
            rule_version_id=None,
            idempotency_key=idempotency_key,
            total_rows=0,
            scored_rows=0,
            approved_count=0,
            rejected_count=0,
            error_count=0,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
            error_message=None,
        )
        self._runs[run.id] = run
        self._candidates[run.id] = []
        return run

    def complete_run(self, *, run: KeywordScoringRun, candidates: list[KeywordCandidate]) -> KeywordScoringRun:
        now = datetime.now(UTC)
        approved_count = sum(1 for candidate in candidates if candidate.scoring_status == KeywordCandidateStatus.APPROVED)
        rejected_count = sum(1 for candidate in candidates if candidate.scoring_status == KeywordCandidateStatus.REJECTED)
        error_count = sum(1 for candidate in candidates if candidate.scoring_status == KeywordCandidateStatus.ERROR)
        completed = run.model_copy(
            update={
                "status": KeywordScoringRunStatus.SUCCEEDED,
                "total_rows": len(candidates),
                "scored_rows": approved_count + rejected_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count,
                "error_count": error_count,
                "completed_at": now,
                "updated_at": now,
            }
        )
        self._runs[completed.id] = completed
        self._candidates[completed.id] = [candidate.model_copy(update={"scoring_run_id": completed.id}) for candidate in candidates]
        return completed

    def fail_run(self, *, run: KeywordScoringRun, error_message: str) -> KeywordScoringRun:
        now = datetime.now(UTC)
        failed = run.model_copy(update={"status": KeywordScoringRunStatus.FAILED, "error_message": error_message, "completed_at": now, "updated_at": now})
        self._runs[failed.id] = failed
        return failed

    def get_run(self, *, workspace_id: UUID, scoring_run_id: UUID) -> KeywordScoringRun | None:
        run = self._runs.get(scoring_run_id)
        return run if run and run.workspace_id == workspace_id else None

    def get_candidate(self, *, workspace_id: UUID, candidate_id: UUID) -> KeywordCandidate | None:
        for candidates in self._candidates.values():
            for candidate in candidates:
                if candidate.id == candidate_id and candidate.workspace_id == workspace_id:
                    return candidate
        return None

    def list_candidates(
        self,
        *,
        workspace_id: UUID,
        scoring_run_id: UUID,
        scoring_status: KeywordCandidateStatus | None,
        min_relevance_score: int | None,
        max_relevance_score: int | None,
        search_term: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[KeywordCandidate], int]:
        run = self.get_run(workspace_id=workspace_id, scoring_run_id=scoring_run_id)
        candidates = list(self._candidates.get(scoring_run_id, [])) if run else []
        if scoring_status is not None:
            candidates = [candidate for candidate in candidates if candidate.scoring_status == scoring_status]
        if min_relevance_score is not None:
            candidates = [candidate for candidate in candidates if candidate.relevance_score is not None and candidate.relevance_score >= min_relevance_score]
        if max_relevance_score is not None:
            candidates = [candidate for candidate in candidates if candidate.relevance_score is not None and candidate.relevance_score <= max_relevance_score]
        if search_term:
            normalized = search_term.strip().lower()
            candidates = [candidate for candidate in candidates if normalized in (candidate.search_term or "").lower()]
        candidates.sort(key=lambda candidate: candidate.created_at)
        total = len(candidates)
        start = (page - 1) * page_size
        return candidates[start : start + page_size], total


class PostgresKeywordScoringRepository(KeywordScoringRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_run_by_idempotency_key(self, *, workspace_id: UUID, idempotency_key: str) -> KeywordScoringRun | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from keyword_scoring_runs where workspace_id = :workspace_id and idempotency_key = :idempotency_key"),
                {"workspace_id": workspace_id, "idempotency_key": idempotency_key},
            ).mappings().first()
        return _run_from_row(row) if row else None

    def create_run(self, *, mapping: ColumnMapping, idempotency_key: str) -> KeywordScoringRun:
        with self._engine.begin() as connection:
            scoring_version = int(
                connection.execute(
                    text("select coalesce(max(scoring_version), 0) + 1 from keyword_scoring_runs where column_mapping_id = :mapping_id"),
                    {"mapping_id": mapping.id},
                ).scalar_one()
            )
            row = connection.execute(
                text(
                    """
                    insert into keyword_scoring_runs (
                        id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id,
                        status, scoring_version, idempotency_key
                    )
                    values (
                        :id, :workspace_id, :product_id, :upload_id, :parse_run_id, :column_mapping_id,
                        'running', :scoring_version, :idempotency_key
                    )
                    returning *
                    """
                ),
                {
                    "id": uuid4(),
                    "workspace_id": mapping.workspace_id,
                    "product_id": mapping.product_id,
                    "upload_id": mapping.upload_id,
                    "parse_run_id": mapping.parse_run_id,
                    "column_mapping_id": mapping.id,
                    "scoring_version": scoring_version,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().one()
        return _run_from_row(row)

    def complete_run(self, *, run: KeywordScoringRun, candidates: list[KeywordCandidate]) -> KeywordScoringRun:
        approved_count = sum(1 for candidate in candidates if candidate.scoring_status == KeywordCandidateStatus.APPROVED)
        rejected_count = sum(1 for candidate in candidates if candidate.scoring_status == KeywordCandidateStatus.REJECTED)
        error_count = sum(1 for candidate in candidates if candidate.scoring_status == KeywordCandidateStatus.ERROR)
        with self._engine.begin() as connection:
            for candidate in candidates:
                connection.execute(
                    text(
                        """
                        insert into keyword_candidates (
                            id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id,
                            scoring_run_id, source_row_id, search_term, search_volume,
                            competitor_rank_values_json, relevance_score, scoring_status, rejection_reason
                        )
                        values (
                            :id, :workspace_id, :product_id, :upload_id, :parse_run_id, :column_mapping_id,
                            :scoring_run_id, :source_row_id, :search_term, :search_volume,
                            cast(:competitor_rank_values_json as jsonb), :relevance_score, :scoring_status,
                            :rejection_reason
                        )
                        """
                    ),
                    _candidate_params(run, candidate),
                )
            row = connection.execute(
                text(
                    """
                    update keyword_scoring_runs
                    set status = 'succeeded',
                        total_rows = :total_rows,
                        scored_rows = :scored_rows,
                        approved_count = :approved_count,
                        rejected_count = :rejected_count,
                        error_count = :error_count,
                        completed_at = now(),
                        updated_at = now()
                    where id = :id
                    returning *
                    """
                ),
                {
                    "id": run.id,
                    "total_rows": len(candidates),
                    "scored_rows": approved_count + rejected_count,
                    "approved_count": approved_count,
                    "rejected_count": rejected_count,
                    "error_count": error_count,
                },
            ).mappings().one()
        return _run_from_row(row)

    def fail_run(self, *, run: KeywordScoringRun, error_message: str) -> KeywordScoringRun:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update keyword_scoring_runs
                    set status = 'failed', error_message = :error_message, completed_at = now(), updated_at = now()
                    where id = :id
                    returning *
                    """
                ),
                {"id": run.id, "error_message": error_message},
            ).mappings().one()
        return _run_from_row(row)

    def get_run(self, *, workspace_id: UUID, scoring_run_id: UUID) -> KeywordScoringRun | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from keyword_scoring_runs where workspace_id = :workspace_id and id = :scoring_run_id"),
                {"workspace_id": workspace_id, "scoring_run_id": scoring_run_id},
            ).mappings().first()
        return _run_from_row(row) if row else None

    def get_candidate(self, *, workspace_id: UUID, candidate_id: UUID) -> KeywordCandidate | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from keyword_candidates where workspace_id = :workspace_id and id = :candidate_id"),
                {"workspace_id": workspace_id, "candidate_id": candidate_id},
            ).mappings().first()
        return _candidate_from_row(row) if row else None

    def list_candidates(
        self,
        *,
        workspace_id: UUID,
        scoring_run_id: UUID,
        scoring_status: KeywordCandidateStatus | None,
        min_relevance_score: int | None,
        max_relevance_score: int | None,
        search_term: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[KeywordCandidate], int]:
        clauses = ["workspace_id = :workspace_id", "scoring_run_id = :scoring_run_id"]
        params: dict[str, object] = {
            "workspace_id": workspace_id,
            "scoring_run_id": scoring_run_id,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        if scoring_status is not None:
            clauses.append("scoring_status = :scoring_status")
            params["scoring_status"] = scoring_status.value
        if min_relevance_score is not None:
            clauses.append("relevance_score >= :min_relevance_score")
            params["min_relevance_score"] = min_relevance_score
        if max_relevance_score is not None:
            clauses.append("relevance_score <= :max_relevance_score")
            params["max_relevance_score"] = max_relevance_score
        if search_term:
            clauses.append("search_term ilike :search_term")
            params["search_term"] = f"%{search_term.strip()}%"
        where_clause = " and ".join(clauses)
        with self._engine.begin() as connection:
            total = connection.execute(text(f"select count(*) from keyword_candidates where {where_clause}"), params).scalar_one()
            rows = connection.execute(
                text(
                    f"""
                    select * from keyword_candidates
                    where {where_clause}
                    order by created_at asc
                    limit :limit offset :offset
                    """
                ),
                params,
            ).mappings().all()
        return [_candidate_from_row(row) for row in rows], int(total)


_local_repository = LocalKeywordScoringRepository()


def get_keyword_scoring_repository() -> KeywordScoringRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresKeywordScoringRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def _run_from_row(row: RowMapping) -> KeywordScoringRun:
    return KeywordScoringRun(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        upload_id=row["upload_id"],
        parse_run_id=row["parse_run_id"],
        column_mapping_id=row["column_mapping_id"],
        status=row["status"],
        scoring_version=row["scoring_version"],
        rule_version_id=row["rule_version_id"],
        idempotency_key=row["idempotency_key"],
        total_rows=row["total_rows"],
        scored_rows=row["scored_rows"],
        approved_count=row["approved_count"],
        rejected_count=row["rejected_count"],
        error_count=row["error_count"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error_message=row["error_message"],
    )


def _candidate_from_row(row: RowMapping) -> KeywordCandidate:
    return KeywordCandidate(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        upload_id=row["upload_id"],
        parse_run_id=row["parse_run_id"],
        column_mapping_id=row["column_mapping_id"],
        scoring_run_id=row["scoring_run_id"],
        source_row_id=row["source_row_id"],
        search_term=row["search_term"],
        search_volume=row["search_volume"],
        competitor_rank_values_json=row["competitor_rank_values_json"],
        relevance_score=row["relevance_score"],
        scoring_status=row["scoring_status"],
        rejection_reason=row["rejection_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _candidate_params(run: KeywordScoringRun, candidate: KeywordCandidate) -> dict:
    return {
        "id": candidate.id,
        "workspace_id": run.workspace_id,
        "product_id": run.product_id,
        "upload_id": run.upload_id,
        "parse_run_id": run.parse_run_id,
        "column_mapping_id": run.column_mapping_id,
        "scoring_run_id": run.id,
        "source_row_id": candidate.source_row_id,
        "search_term": candidate.search_term,
        "search_volume": candidate.search_volume,
        "competitor_rank_values_json": _json_dumps(candidate.competitor_rank_values_json),
        "relevance_score": candidate.relevance_score,
        "scoring_status": candidate.scoring_status.value,
        "rejection_reason": candidate.rejection_reason,
    }


def _next_scoring_version(runs: list[KeywordScoringRun]) -> int:
    return max((run.scoring_version for run in runs), default=0) + 1


def _json_dumps(value) -> str:
    import json

    def default(item):
        if isinstance(item, Decimal):
            return str(item)
        raise TypeError(f"Object of type {type(item).__name__} is not JSON serializable")

    return json.dumps(value, default=default)
