from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.column_mapping import (
    ColumnInferredDataType,
    ColumnMapping,
    ColumnMappingStatus,
    ColumnMappingType,
    ColumnProfile,
    ColumnProfileColumn,
    ColumnProfileStatus,
)
from apps.api.app.schemas.upload_parsing import UploadParseRun


class ColumnMappingRepository(ABC):
    @abstractmethod
    def get_profile_by_parse_run(self, *, workspace_id: UUID, parse_run_id: UUID) -> tuple[ColumnProfile, list[ColumnProfileColumn]] | None:
        raise NotImplementedError

    @abstractmethod
    def get_profile_for_upload(self, *, workspace_id: UUID, upload_id: UUID) -> tuple[ColumnProfile, list[ColumnProfileColumn]] | None:
        raise NotImplementedError

    @abstractmethod
    def get_profile(self, *, workspace_id: UUID, upload_id: UUID, column_profile_id: UUID) -> tuple[ColumnProfile, list[ColumnProfileColumn]] | None:
        raise NotImplementedError

    @abstractmethod
    def create_profile(
        self,
        *,
        parse_run: UploadParseRun,
        total_columns: int,
        total_rows_sampled: int,
        columns: list[dict],
    ) -> tuple[ColumnProfile, list[ColumnProfileColumn]]:
        raise NotImplementedError

    @abstractmethod
    def create_mapping(
        self,
        *,
        profile: ColumnProfile,
        mapping_json: dict,
        validation_messages: list[dict],
        status: ColumnMappingStatus,
        created_by: str,
    ) -> ColumnMapping:
        raise NotImplementedError

    @abstractmethod
    def list_mappings(self, *, workspace_id: UUID, upload_id: UUID, page: int, page_size: int) -> tuple[list[ColumnMapping], int]:
        raise NotImplementedError

    @abstractmethod
    def get_mapping(self, *, workspace_id: UUID, mapping_id: UUID) -> ColumnMapping | None:
        raise NotImplementedError

    @abstractmethod
    def approve_mapping(self, *, workspace_id: UUID, mapping_id: UUID) -> ColumnMapping:
        raise NotImplementedError


class LocalColumnMappingRepository(ColumnMappingRepository):
    def __init__(self) -> None:
        self._profiles: dict[UUID, ColumnProfile] = {}
        self._columns: dict[UUID, list[ColumnProfileColumn]] = {}
        self._mappings: dict[UUID, ColumnMapping] = {}

    def get_profile_by_parse_run(self, *, workspace_id: UUID, parse_run_id: UUID) -> tuple[ColumnProfile, list[ColumnProfileColumn]] | None:
        for profile in self._profiles.values():
            if profile.workspace_id == workspace_id and profile.parse_run_id == parse_run_id:
                return profile, self._columns.get(profile.id, [])
        return None

    def get_profile_for_upload(self, *, workspace_id: UUID, upload_id: UUID) -> tuple[ColumnProfile, list[ColumnProfileColumn]] | None:
        profiles = [profile for profile in self._profiles.values() if profile.workspace_id == workspace_id and profile.upload_id == upload_id]
        if not profiles:
            return None
        profile = sorted(profiles, key=lambda item: item.created_at, reverse=True)[0]
        return profile, self._columns.get(profile.id, [])

    def get_profile(self, *, workspace_id: UUID, upload_id: UUID, column_profile_id: UUID) -> tuple[ColumnProfile, list[ColumnProfileColumn]] | None:
        profile = self._profiles.get(column_profile_id)
        if profile is None or profile.workspace_id != workspace_id or profile.upload_id != upload_id:
            return None
        return profile, self._columns.get(profile.id, [])

    def create_profile(
        self,
        *,
        parse_run: UploadParseRun,
        total_columns: int,
        total_rows_sampled: int,
        columns: list[dict],
    ) -> tuple[ColumnProfile, list[ColumnProfileColumn]]:
        existing = self.get_profile_by_parse_run(workspace_id=parse_run.workspace_id, parse_run_id=parse_run.id)
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        profile = ColumnProfile(
            id=uuid4(),
            workspace_id=parse_run.workspace_id,
            product_id=parse_run.product_id,
            upload_id=parse_run.upload_id,
            parse_run_id=parse_run.id,
            status=ColumnProfileStatus.GENERATED,
            total_columns=total_columns,
            total_rows_sampled=total_rows_sampled,
            created_at=now,
            updated_at=now,
        )
        profile_columns = [
            ColumnProfileColumn(
                id=uuid4(),
                workspace_id=profile.workspace_id,
                product_id=profile.product_id,
                upload_id=profile.upload_id,
                parse_run_id=profile.parse_run_id,
                column_profile_id=profile.id,
                original_column_name=column["original_column_name"],
                normalized_column_name=column["normalized_column_name"],
                column_index=column["column_index"],
                non_null_count=column["non_null_count"],
                sample_values_json=column["sample_values_json"],
                inferred_data_type=column["inferred_data_type"],
                created_at=now,
            )
            for column in columns
        ]
        self._profiles[profile.id] = profile
        self._columns[profile.id] = profile_columns
        return profile, profile_columns

    def create_mapping(
        self,
        *,
        profile: ColumnProfile,
        mapping_json: dict,
        validation_messages: list[dict],
        status: ColumnMappingStatus,
        created_by: str,
    ) -> ColumnMapping:
        version = _next_mapping_version([mapping for mapping in self._mappings.values() if mapping.column_profile_id == profile.id])
        mapping = ColumnMapping(
            id=uuid4(),
            workspace_id=profile.workspace_id,
            product_id=profile.product_id,
            upload_id=profile.upload_id,
            parse_run_id=profile.parse_run_id,
            column_profile_id=profile.id,
            status=status,
            mapping_version=version,
            mapping_type=ColumnMappingType.MANUAL,
            mapping_json=mapping_json,
            validation_errors_json=validation_messages,
            created_by=_uuid_or_none(created_by),
            created_at=datetime.now(UTC),
            approved_at=None,
        )
        self._mappings[mapping.id] = mapping
        return mapping

    def list_mappings(self, *, workspace_id: UUID, upload_id: UUID, page: int, page_size: int) -> tuple[list[ColumnMapping], int]:
        mappings = [mapping for mapping in self._mappings.values() if mapping.workspace_id == workspace_id and mapping.upload_id == upload_id]
        mappings.sort(key=lambda mapping: (mapping.created_at, mapping.mapping_version), reverse=True)
        total = len(mappings)
        start = (page - 1) * page_size
        return mappings[start : start + page_size], total

    def get_mapping(self, *, workspace_id: UUID, mapping_id: UUID) -> ColumnMapping | None:
        mapping = self._mappings.get(mapping_id)
        return mapping if mapping and mapping.workspace_id == workspace_id else None

    def approve_mapping(self, *, workspace_id: UUID, mapping_id: UUID) -> ColumnMapping:
        mapping = self.get_mapping(workspace_id=workspace_id, mapping_id=mapping_id)
        if mapping is None:
            raise ApiError(code="COLUMN_MAPPING_NOT_FOUND", message="Column mapping was not found.", status_code=404)
        if mapping.status != ColumnMappingStatus.VALID:
            raise ApiError(code="COLUMN_MAPPING_NOT_APPROVABLE", message="Only valid mappings can be approved.", status_code=409)
        now = datetime.now(UTC)
        for existing in list(self._mappings.values()):
            if existing.column_profile_id == mapping.column_profile_id and existing.status == ColumnMappingStatus.APPROVED:
                self._mappings[existing.id] = existing.model_copy(update={"status": ColumnMappingStatus.SUPERSEDED})
        approved = mapping.model_copy(update={"status": ColumnMappingStatus.APPROVED, "approved_at": now})
        self._mappings[approved.id] = approved
        return approved


class PostgresColumnMappingRepository(ColumnMappingRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_profile_by_parse_run(self, *, workspace_id: UUID, parse_run_id: UUID) -> tuple[ColumnProfile, list[ColumnProfileColumn]] | None:
        with self._engine.begin() as connection:
            profile_row = connection.execute(
                text("select * from upload_column_profiles where workspace_id = :workspace_id and parse_run_id = :parse_run_id"),
                {"workspace_id": workspace_id, "parse_run_id": parse_run_id},
            ).mappings().first()
            if profile_row is None:
                return None
            columns = _profile_columns(connection, profile_row["id"])
        return _profile_from_row(profile_row), columns

    def get_profile_for_upload(self, *, workspace_id: UUID, upload_id: UUID) -> tuple[ColumnProfile, list[ColumnProfileColumn]] | None:
        with self._engine.begin() as connection:
            profile_row = connection.execute(
                text(
                    """
                    select * from upload_column_profiles
                    where workspace_id = :workspace_id and upload_id = :upload_id
                    order by created_at desc
                    limit 1
                    """
                ),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            ).mappings().first()
            if profile_row is None:
                return None
            columns = _profile_columns(connection, profile_row["id"])
        return _profile_from_row(profile_row), columns

    def get_profile(self, *, workspace_id: UUID, upload_id: UUID, column_profile_id: UUID) -> tuple[ColumnProfile, list[ColumnProfileColumn]] | None:
        with self._engine.begin() as connection:
            profile_row = connection.execute(
                text(
                    """
                    select * from upload_column_profiles
                    where id = :column_profile_id and workspace_id = :workspace_id and upload_id = :upload_id
                    """
                ),
                {"column_profile_id": column_profile_id, "workspace_id": workspace_id, "upload_id": upload_id},
            ).mappings().first()
            if profile_row is None:
                return None
            columns = _profile_columns(connection, profile_row["id"])
        return _profile_from_row(profile_row), columns

    def create_profile(
        self,
        *,
        parse_run: UploadParseRun,
        total_columns: int,
        total_rows_sampled: int,
        columns: list[dict],
    ) -> tuple[ColumnProfile, list[ColumnProfileColumn]]:
        existing = self.get_profile_by_parse_run(workspace_id=parse_run.workspace_id, parse_run_id=parse_run.id)
        if existing is not None:
            return existing
        profile_id = uuid4()
        with self._engine.begin() as connection:
            profile_row = connection.execute(
                text(
                    """
                    insert into upload_column_profiles (
                        id, workspace_id, product_id, upload_id, parse_run_id, status,
                        total_columns, total_rows_sampled
                    )
                    values (
                        :id, :workspace_id, :product_id, :upload_id, :parse_run_id, 'generated',
                        :total_columns, :total_rows_sampled
                    )
                    on conflict (parse_run_id) do update
                    set updated_at = upload_column_profiles.updated_at
                    returning *
                    """
                ),
                {
                    "id": profile_id,
                    "workspace_id": parse_run.workspace_id,
                    "product_id": parse_run.product_id,
                    "upload_id": parse_run.upload_id,
                    "parse_run_id": parse_run.id,
                    "total_columns": total_columns,
                    "total_rows_sampled": total_rows_sampled,
                },
            ).mappings().one()
            if profile_row["id"] == profile_id:
                for column in columns:
                    connection.execute(
                        text(
                            """
                            insert into upload_column_profile_columns (
                                id, workspace_id, product_id, upload_id, parse_run_id, column_profile_id,
                                original_column_name, normalized_column_name, column_index, non_null_count,
                                sample_values_json, inferred_data_type
                            )
                            values (
                                :id, :workspace_id, :product_id, :upload_id, :parse_run_id, :column_profile_id,
                                :original_column_name, :normalized_column_name, :column_index, :non_null_count,
                                cast(:sample_values_json as jsonb), :inferred_data_type
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "workspace_id": parse_run.workspace_id,
                            "product_id": parse_run.product_id,
                            "upload_id": parse_run.upload_id,
                            "parse_run_id": parse_run.id,
                            "column_profile_id": profile_row["id"],
                            "original_column_name": column["original_column_name"],
                            "normalized_column_name": column["normalized_column_name"],
                            "column_index": column["column_index"],
                            "non_null_count": column["non_null_count"],
                            "sample_values_json": _json_dumps(column["sample_values_json"]),
                            "inferred_data_type": column["inferred_data_type"].value,
                        },
                    )
            profile_columns = _profile_columns(connection, profile_row["id"])
        return _profile_from_row(profile_row), profile_columns

    def create_mapping(
        self,
        *,
        profile: ColumnProfile,
        mapping_json: dict,
        validation_messages: list[dict],
        status: ColumnMappingStatus,
        created_by: str,
    ) -> ColumnMapping:
        with self._engine.begin() as connection:
            version = int(
                connection.execute(
                    text("select coalesce(max(mapping_version), 0) + 1 from upload_column_mappings where column_profile_id = :profile_id"),
                    {"profile_id": profile.id},
                ).scalar_one()
            )
            row = connection.execute(
                text(
                    """
                    insert into upload_column_mappings (
                        id, workspace_id, product_id, upload_id, parse_run_id, column_profile_id,
                        status, mapping_version, mapping_type, mapping_json, validation_errors_json,
                        created_by
                    )
                    values (
                        :id, :workspace_id, :product_id, :upload_id, :parse_run_id, :column_profile_id,
                        :status, :mapping_version, 'manual', cast(:mapping_json as jsonb),
                        cast(:validation_errors_json as jsonb), :created_by
                    )
                    returning *
                    """
                ),
                {
                    "id": uuid4(),
                    "workspace_id": profile.workspace_id,
                    "product_id": profile.product_id,
                    "upload_id": profile.upload_id,
                    "parse_run_id": profile.parse_run_id,
                    "column_profile_id": profile.id,
                    "status": status.value,
                    "mapping_version": version,
                    "mapping_json": _json_dumps(mapping_json),
                    "validation_errors_json": _json_dumps(validation_messages),
                    "created_by": _uuid_or_none(created_by),
                },
            ).mappings().one()
        return _mapping_from_row(row)

    def list_mappings(self, *, workspace_id: UUID, upload_id: UUID, page: int, page_size: int) -> tuple[list[ColumnMapping], int]:
        params = {"workspace_id": workspace_id, "upload_id": upload_id, "limit": page_size, "offset": (page - 1) * page_size}
        with self._engine.begin() as connection:
            total = connection.execute(
                text("select count(*) from upload_column_mappings where workspace_id = :workspace_id and upload_id = :upload_id"),
                params,
            ).scalar_one()
            rows = connection.execute(
                text(
                    """
                    select * from upload_column_mappings
                    where workspace_id = :workspace_id and upload_id = :upload_id
                    order by created_at desc, mapping_version desc
                    limit :limit offset :offset
                    """
                ),
                params,
            ).mappings().all()
        return [_mapping_from_row(row) for row in rows], int(total)

    def get_mapping(self, *, workspace_id: UUID, mapping_id: UUID) -> ColumnMapping | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from upload_column_mappings where workspace_id = :workspace_id and id = :mapping_id"),
                {"workspace_id": workspace_id, "mapping_id": mapping_id},
            ).mappings().first()
        return _mapping_from_row(row) if row else None

    def approve_mapping(self, *, workspace_id: UUID, mapping_id: UUID) -> ColumnMapping:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from upload_column_mappings where workspace_id = :workspace_id and id = :mapping_id for update"),
                {"workspace_id": workspace_id, "mapping_id": mapping_id},
            ).mappings().first()
            if row is None:
                raise ApiError(code="COLUMN_MAPPING_NOT_FOUND", message="Column mapping was not found.", status_code=404)
            if row["status"] != ColumnMappingStatus.VALID.value:
                raise ApiError(code="COLUMN_MAPPING_NOT_APPROVABLE", message="Only valid mappings can be approved.", status_code=409)
            connection.execute(
                text(
                    """
                    update upload_column_mappings
                    set status = 'superseded'
                    where workspace_id = :workspace_id
                      and column_profile_id = :column_profile_id
                      and status = 'approved'
                    """
                ),
                {"workspace_id": workspace_id, "column_profile_id": row["column_profile_id"]},
            )
            approved_row = connection.execute(
                text(
                    """
                    update upload_column_mappings
                    set status = 'approved', approved_at = now()
                    where id = :mapping_id
                    returning *
                    """
                ),
                {"mapping_id": mapping_id},
            ).mappings().one()
        return _mapping_from_row(approved_row)


_local_repository = LocalColumnMappingRepository()


def get_column_mapping_repository() -> ColumnMappingRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresColumnMappingRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def _profile_columns(connection, profile_id: UUID) -> list[ColumnProfileColumn]:
    rows = connection.execute(
        text("select * from upload_column_profile_columns where column_profile_id = :profile_id order by column_index"),
        {"profile_id": profile_id},
    ).mappings().all()
    return [_column_from_row(row) for row in rows]


def _profile_from_row(row: RowMapping) -> ColumnProfile:
    return ColumnProfile(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        upload_id=row["upload_id"],
        parse_run_id=row["parse_run_id"],
        status=row["status"],
        total_columns=row["total_columns"],
        total_rows_sampled=row["total_rows_sampled"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _column_from_row(row: RowMapping) -> ColumnProfileColumn:
    return ColumnProfileColumn(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        upload_id=row["upload_id"],
        parse_run_id=row["parse_run_id"],
        column_profile_id=row["column_profile_id"],
        original_column_name=row["original_column_name"],
        normalized_column_name=row["normalized_column_name"],
        column_index=row["column_index"],
        non_null_count=row["non_null_count"],
        sample_values_json=row["sample_values_json"],
        inferred_data_type=row["inferred_data_type"],
        created_at=row["created_at"],
    )


def _mapping_from_row(row: RowMapping) -> ColumnMapping:
    return ColumnMapping(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        upload_id=row["upload_id"],
        parse_run_id=row["parse_run_id"],
        column_profile_id=row["column_profile_id"],
        status=row["status"],
        mapping_version=row["mapping_version"],
        mapping_type=row["mapping_type"],
        mapping_json=row["mapping_json"],
        validation_errors_json=row["validation_errors_json"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        approved_at=row["approved_at"],
    )


def _next_mapping_version(mappings: list[ColumnMapping]) -> int:
    return max((mapping.mapping_version for mapping in mappings), default=0) + 1


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _json_dumps(value) -> str:
    import json

    return json.dumps(value)
