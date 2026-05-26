from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.keyword_review import ApprovedKeywordSet, ApprovedKeywordSetItem, KeywordCandidateOverride


class KeywordReviewRepository(ABC):
    @abstractmethod
    def get_override_for_candidate(self, *, workspace_id: UUID, keyword_candidate_id: UUID) -> KeywordCandidateOverride | None:
        raise NotImplementedError

    @abstractmethod
    def list_overrides_for_scoring_run(self, *, workspace_id: UUID, scoring_run_id: UUID) -> list[KeywordCandidateOverride]:
        raise NotImplementedError

    @abstractmethod
    def create_override(self, *, override: KeywordCandidateOverride) -> KeywordCandidateOverride:
        raise NotImplementedError

    @abstractmethod
    def create_keyword_set(self, *, keyword_set: ApprovedKeywordSet, items: list[ApprovedKeywordSetItem]) -> ApprovedKeywordSet:
        raise NotImplementedError

    @abstractmethod
    def get_keyword_set(self, *, workspace_id: UUID, keyword_set_id: UUID) -> ApprovedKeywordSet | None:
        raise NotImplementedError

    @abstractmethod
    def list_keyword_set_items(
        self,
        *,
        workspace_id: UUID,
        keyword_set_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ApprovedKeywordSetItem], int]:
        raise NotImplementedError


class LocalKeywordReviewRepository(KeywordReviewRepository):
    def __init__(self) -> None:
        self._overrides: dict[UUID, KeywordCandidateOverride] = {}
        self._keyword_sets: dict[UUID, ApprovedKeywordSet] = {}
        self._keyword_set_items: dict[UUID, list[ApprovedKeywordSetItem]] = {}

    def get_override_for_candidate(self, *, workspace_id: UUID, keyword_candidate_id: UUID) -> KeywordCandidateOverride | None:
        override = self._overrides.get(keyword_candidate_id)
        return override if override and override.workspace_id == workspace_id else None

    def list_overrides_for_scoring_run(self, *, workspace_id: UUID, scoring_run_id: UUID) -> list[KeywordCandidateOverride]:
        return [
            override
            for override in self._overrides.values()
            if override.workspace_id == workspace_id and override.scoring_run_id == scoring_run_id
        ]

    def create_override(self, *, override: KeywordCandidateOverride) -> KeywordCandidateOverride:
        if override.keyword_candidate_id in self._overrides:
            raise ApiError(code="KEYWORD_CANDIDATE_OVERRIDE_EXISTS", message="Keyword candidate already has an override.", status_code=409)
        self._overrides[override.keyword_candidate_id] = override
        return override

    def create_keyword_set(self, *, keyword_set: ApprovedKeywordSet, items: list[ApprovedKeywordSetItem]) -> ApprovedKeywordSet:
        self._keyword_sets[keyword_set.id] = keyword_set
        self._keyword_set_items[keyword_set.id] = list(items)
        return keyword_set

    def get_keyword_set(self, *, workspace_id: UUID, keyword_set_id: UUID) -> ApprovedKeywordSet | None:
        keyword_set = self._keyword_sets.get(keyword_set_id)
        return keyword_set if keyword_set and keyword_set.workspace_id == workspace_id else None

    def list_keyword_set_items(
        self,
        *,
        workspace_id: UUID,
        keyword_set_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ApprovedKeywordSetItem], int]:
        keyword_set = self.get_keyword_set(workspace_id=workspace_id, keyword_set_id=keyword_set_id)
        items = list(self._keyword_set_items.get(keyword_set_id, [])) if keyword_set else []
        items.sort(key=lambda item: item.created_at)
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total


class PostgresKeywordReviewRepository(KeywordReviewRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_override_for_candidate(self, *, workspace_id: UUID, keyword_candidate_id: UUID) -> KeywordCandidateOverride | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    select * from keyword_candidate_overrides
                    where workspace_id = :workspace_id and keyword_candidate_id = :keyword_candidate_id
                    """
                ),
                {"workspace_id": workspace_id, "keyword_candidate_id": keyword_candidate_id},
            ).mappings().first()
        return _override_from_row(row) if row else None

    def list_overrides_for_scoring_run(self, *, workspace_id: UUID, scoring_run_id: UUID) -> list[KeywordCandidateOverride]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    select * from keyword_candidate_overrides
                    where workspace_id = :workspace_id and scoring_run_id = :scoring_run_id
                    """
                ),
                {"workspace_id": workspace_id, "scoring_run_id": scoring_run_id},
            ).mappings().all()
        return [_override_from_row(row) for row in rows]

    def create_override(self, *, override: KeywordCandidateOverride) -> KeywordCandidateOverride:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into keyword_candidate_overrides (
                        id, workspace_id, product_id, scoring_run_id, keyword_candidate_id,
                        override_action, original_scoring_status, new_status, reason, created_by, created_at
                    )
                    values (
                        :id, :workspace_id, :product_id, :scoring_run_id, :keyword_candidate_id,
                        :override_action, :original_scoring_status, :new_status, :reason, :created_by, :created_at
                    )
                    returning *
                    """
                ),
                _override_params(override),
            ).mappings().one()
        return _override_from_row(row)

    def create_keyword_set(self, *, keyword_set: ApprovedKeywordSet, items: list[ApprovedKeywordSetItem]) -> ApprovedKeywordSet:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into approved_keyword_sets (
                        id, workspace_id, product_id, scoring_run_id, column_mapping_id,
                        name, status, keyword_count, created_by, created_at, approved_at
                    )
                    values (
                        :id, :workspace_id, :product_id, :scoring_run_id, :column_mapping_id,
                        :name, :status, :keyword_count, :created_by, :created_at, :approved_at
                    )
                    returning *
                    """
                ),
                _keyword_set_params(keyword_set),
            ).mappings().one()
            for item in items:
                connection.execute(
                    text(
                        """
                        insert into approved_keyword_set_items (
                            id, workspace_id, product_id, approved_keyword_set_id, scoring_run_id,
                            keyword_candidate_id, search_term, search_volume, relevance_score,
                            source_status, final_status, override_id, created_at
                        )
                        values (
                            :id, :workspace_id, :product_id, :approved_keyword_set_id, :scoring_run_id,
                            :keyword_candidate_id, :search_term, :search_volume, :relevance_score,
                            :source_status, :final_status, :override_id, :created_at
                        )
                        """
                    ),
                    _keyword_set_item_params(item),
                )
        return _keyword_set_from_row(row)

    def get_keyword_set(self, *, workspace_id: UUID, keyword_set_id: UUID) -> ApprovedKeywordSet | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from approved_keyword_sets where workspace_id = :workspace_id and id = :keyword_set_id"),
                {"workspace_id": workspace_id, "keyword_set_id": keyword_set_id},
            ).mappings().first()
        return _keyword_set_from_row(row) if row else None

    def list_keyword_set_items(
        self,
        *,
        workspace_id: UUID,
        keyword_set_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ApprovedKeywordSetItem], int]:
        params = {
            "workspace_id": workspace_id,
            "keyword_set_id": keyword_set_id,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        with self._engine.begin() as connection:
            total = connection.execute(
                text(
                    """
                    select count(*) from approved_keyword_set_items
                    where workspace_id = :workspace_id and approved_keyword_set_id = :keyword_set_id
                    """
                ),
                params,
            ).scalar_one()
            rows = connection.execute(
                text(
                    """
                    select * from approved_keyword_set_items
                    where workspace_id = :workspace_id and approved_keyword_set_id = :keyword_set_id
                    order by created_at asc
                    limit :limit offset :offset
                    """
                ),
                params,
            ).mappings().all()
        return [_keyword_set_item_from_row(row) for row in rows], int(total)


_local_repository = LocalKeywordReviewRepository()


def get_keyword_review_repository() -> KeywordReviewRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresKeywordReviewRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def _override_from_row(row: RowMapping) -> KeywordCandidateOverride:
    return KeywordCandidateOverride(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        scoring_run_id=row["scoring_run_id"],
        keyword_candidate_id=row["keyword_candidate_id"],
        override_action=row["override_action"],
        original_scoring_status=row["original_scoring_status"],
        new_status=row["new_status"],
        reason=row["reason"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _keyword_set_from_row(row: RowMapping) -> ApprovedKeywordSet:
    return ApprovedKeywordSet(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        scoring_run_id=row["scoring_run_id"],
        column_mapping_id=row["column_mapping_id"],
        name=row["name"],
        status=row["status"],
        keyword_count=row["keyword_count"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        approved_at=row["approved_at"],
    )


def _keyword_set_item_from_row(row: RowMapping) -> ApprovedKeywordSetItem:
    return ApprovedKeywordSetItem(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        approved_keyword_set_id=row["approved_keyword_set_id"],
        scoring_run_id=row["scoring_run_id"],
        keyword_candidate_id=row["keyword_candidate_id"],
        search_term=row["search_term"],
        search_volume=row["search_volume"],
        relevance_score=row["relevance_score"],
        source_status=row["source_status"],
        final_status=row["final_status"],
        override_id=row["override_id"],
        created_at=row["created_at"],
    )


def _override_params(override: KeywordCandidateOverride) -> dict:
    return {
        "id": override.id,
        "workspace_id": override.workspace_id,
        "product_id": override.product_id,
        "scoring_run_id": override.scoring_run_id,
        "keyword_candidate_id": override.keyword_candidate_id,
        "override_action": override.override_action.value,
        "original_scoring_status": override.original_scoring_status.value,
        "new_status": override.new_status.value,
        "reason": override.reason,
        "created_by": override.created_by,
        "created_at": override.created_at,
    }


def _keyword_set_params(keyword_set: ApprovedKeywordSet) -> dict:
    return {
        "id": keyword_set.id,
        "workspace_id": keyword_set.workspace_id,
        "product_id": keyword_set.product_id,
        "scoring_run_id": keyword_set.scoring_run_id,
        "column_mapping_id": keyword_set.column_mapping_id,
        "name": keyword_set.name,
        "status": keyword_set.status.value,
        "keyword_count": keyword_set.keyword_count,
        "created_by": keyword_set.created_by,
        "created_at": keyword_set.created_at,
        "approved_at": keyword_set.approved_at,
    }


def _keyword_set_item_params(item: ApprovedKeywordSetItem) -> dict:
    return {
        "id": item.id,
        "workspace_id": item.workspace_id,
        "product_id": item.product_id,
        "approved_keyword_set_id": item.approved_keyword_set_id,
        "scoring_run_id": item.scoring_run_id,
        "keyword_candidate_id": item.keyword_candidate_id,
        "search_term": item.search_term,
        "search_volume": item.search_volume,
        "relevance_score": item.relevance_score,
        "source_status": item.source_status.value,
        "final_status": item.final_status.value,
        "override_id": item.override_id,
        "created_at": item.created_at,
    }
