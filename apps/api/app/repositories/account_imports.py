from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.account_imports import (
    AccountImport,
    AccountImportEntity,
    AccountImportStatus,
    DetectionConfidence,
    ProductMappingSuggestion,
    ReportType,
)
from apps.api.app.schemas.uploads import UploadSourceType


class AccountImportRepository(ABC):
    @abstractmethod
    def create_import(self, *, import_record: AccountImport) -> AccountImport:
        raise NotImplementedError

    @abstractmethod
    def insert_entities(self, *, entities: list[AccountImportEntity]) -> None:
        raise NotImplementedError

    @abstractmethod
    def insert_mapping_suggestions(self, *, suggestions: list[ProductMappingSuggestion]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_import(self, *, workspace_id: UUID, account_import_id: UUID) -> AccountImport | None:
        raise NotImplementedError

    @abstractmethod
    def list_imports(self, *, workspace_id: UUID) -> list[AccountImport]:
        raise NotImplementedError

    @abstractmethod
    def list_entities(self, *, workspace_id: UUID, account_import_id: UUID) -> list[AccountImportEntity]:
        raise NotImplementedError

    @abstractmethod
    def list_mapping_suggestions(self, *, workspace_id: UUID, account_import_id: UUID) -> list[ProductMappingSuggestion]:
        raise NotImplementedError

    @abstractmethod
    def delete_by_upload(self, *, workspace_id: UUID, upload_id: UUID) -> None:
        raise NotImplementedError


class LocalAccountImportRepository(AccountImportRepository):
    def __init__(self) -> None:
        self._imports: dict[UUID, AccountImport] = {}
        self._entities: dict[UUID, list[AccountImportEntity]] = {}
        self._suggestions: dict[UUID, list[ProductMappingSuggestion]] = {}

    def create_import(self, *, import_record: AccountImport) -> AccountImport:
        self._imports[import_record.id] = import_record
        return import_record

    def insert_entities(self, *, entities: list[AccountImportEntity]) -> None:
        for entity in entities:
            self._entities.setdefault(entity.account_import_id, []).append(entity)

    def insert_mapping_suggestions(self, *, suggestions: list[ProductMappingSuggestion]) -> None:
        for suggestion in suggestions:
            self._suggestions.setdefault(suggestion.account_import_id, []).append(suggestion)

    def get_import(self, *, workspace_id: UUID, account_import_id: UUID) -> AccountImport | None:
        item = self._imports.get(account_import_id)
        return item if item and item.workspace_id == workspace_id else None

    def list_imports(self, *, workspace_id: UUID) -> list[AccountImport]:
        return sorted([item for item in self._imports.values() if item.workspace_id == workspace_id], key=lambda item: item.created_at, reverse=True)

    def list_entities(self, *, workspace_id: UUID, account_import_id: UUID) -> list[AccountImportEntity]:
        return [item for item in self._entities.get(account_import_id, []) if item.workspace_id == workspace_id]

    def list_mapping_suggestions(self, *, workspace_id: UUID, account_import_id: UUID) -> list[ProductMappingSuggestion]:
        return [item for item in self._suggestions.get(account_import_id, []) if item.workspace_id == workspace_id]

    def delete_by_upload(self, *, workspace_id: UUID, upload_id: UUID) -> None:
        import_ids = [item_id for item_id, item in self._imports.items() if item.workspace_id == workspace_id and item.upload_id == upload_id]
        for import_id in import_ids:
            self._imports.pop(import_id, None)
            self._entities.pop(import_id, None)
            self._suggestions.pop(import_id, None)


class PostgresAccountImportRepository(AccountImportRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_import(self, *, import_record: AccountImport) -> AccountImport:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into account_imports (
                        id, workspace_id, upload_id, parse_run_id, report_type, status,
                        detected_report_type, detection_confidence, total_rows, processed_rows,
                        error_rows, data_quality_warnings_json, created_by, error_message, created_at, updated_at
                    )
                    values (
                        :id, :workspace_id, :upload_id, :parse_run_id, :report_type, :status,
                        :detected_report_type, :detection_confidence, :total_rows, :processed_rows,
                        :error_rows, :data_quality_warnings_json, :created_by, :error_message, :created_at, :updated_at
                    )
                    returning *
                    """
                ),
                _import_params(import_record),
            ).mappings().one()
        return _import_from_row(row)

    def insert_entities(self, *, entities: list[AccountImportEntity]) -> None:
        if not entities:
            return
        statement = text(
            """
            insert into account_import_entities (
                id, workspace_id, account_import_id, product_id, asin, sku, product_name,
                campaign_name, ad_group_name, targeting, customer_search_term, entity_type,
                entity_key, resolution_status, metrics_json, raw_row_refs_json, created_at
            )
            values (
                :id, :workspace_id, :account_import_id, :product_id, :asin, :sku, :product_name,
                :campaign_name, :ad_group_name, :targeting, :customer_search_term, :entity_type,
                :entity_key, :resolution_status, :metrics_json, :raw_row_refs_json, :created_at
            )
            """
        )
        with self._engine.begin() as connection:
            connection.execute(statement, [_entity_params(item) for item in entities])

    def insert_mapping_suggestions(self, *, suggestions: list[ProductMappingSuggestion]) -> None:
        if not suggestions:
            return
        statement = text(
            """
            insert into product_mapping_suggestions (
                id, workspace_id, account_import_id, asin, sku, detected_product_name,
                suggested_product_id, status, created_at, updated_at
            )
            values (
                :id, :workspace_id, :account_import_id, :asin, :sku, :detected_product_name,
                :suggested_product_id, :status, :created_at, :updated_at
            )
            """
        )
        with self._engine.begin() as connection:
            connection.execute(statement, [_suggestion_params(item) for item in suggestions])

    def get_import(self, *, workspace_id: UUID, account_import_id: UUID) -> AccountImport | None:
        with self._engine.begin() as connection:
            row = connection.execute(text("select * from account_imports where workspace_id = :workspace_id and id = :id"), {"workspace_id": workspace_id, "id": account_import_id}).mappings().first()
        return _import_from_row(row) if row else None

    def list_imports(self, *, workspace_id: UUID) -> list[AccountImport]:
        with self._engine.begin() as connection:
            rows = connection.execute(text("select * from account_imports where workspace_id = :workspace_id order by created_at desc"), {"workspace_id": workspace_id}).mappings().all()
        return [_import_from_row(row) for row in rows]

    def list_entities(self, *, workspace_id: UUID, account_import_id: UUID) -> list[AccountImportEntity]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text("select * from account_import_entities where workspace_id = :workspace_id and account_import_id = :account_import_id order by entity_type, entity_key"),
                {"workspace_id": workspace_id, "account_import_id": account_import_id},
            ).mappings().all()
        return [_entity_from_row(row) for row in rows]

    def list_mapping_suggestions(self, *, workspace_id: UUID, account_import_id: UUID) -> list[ProductMappingSuggestion]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text("select * from product_mapping_suggestions where workspace_id = :workspace_id and account_import_id = :account_import_id order by created_at asc"),
                {"workspace_id": workspace_id, "account_import_id": account_import_id},
            ).mappings().all()
        return [_suggestion_from_row(row) for row in rows]

    def delete_by_upload(self, *, workspace_id: UUID, upload_id: UUID) -> None:
        with self._engine.begin() as connection:
            import_ids = [
                row[0]
                for row in connection.execute(
                    text("select id from account_imports where workspace_id = :workspace_id and upload_id = :upload_id"),
                    {"workspace_id": workspace_id, "upload_id": upload_id},
                ).all()
            ]
            for import_id in import_ids:
                connection.execute(
                    text("delete from account_import_entities where workspace_id = :workspace_id and account_import_id = :account_import_id"),
                    {"workspace_id": workspace_id, "account_import_id": import_id},
                )
                connection.execute(
                    text("delete from product_mapping_suggestions where workspace_id = :workspace_id and account_import_id = :account_import_id"),
                    {"workspace_id": workspace_id, "account_import_id": import_id},
                )
            connection.execute(
                text("delete from account_imports where workspace_id = :workspace_id and upload_id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            )


_local_repository = LocalAccountImportRepository()


def get_account_import_repository() -> AccountImportRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresAccountImportRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(code="DATABASE_NOT_CONFIGURED", message="DATABASE_URL must be configured outside local and test environments.", status_code=503)


def new_account_import(
    *,
    workspace_id: UUID,
    upload_id: UUID,
    parse_run_id: UUID,
    report_type: UploadSourceType,
    detected_report_type: ReportType,
    detection_confidence: DetectionConfidence,
    total_rows: int,
    processed_rows: int,
    error_rows: int,
    warnings: list[dict],
    created_by: str,
    needs_mapping: bool,
) -> AccountImport:
    now = datetime.now(UTC)
    return AccountImport(
        id=uuid4(),
        workspace_id=workspace_id,
        upload_id=upload_id,
        parse_run_id=parse_run_id,
        report_type=report_type,
        status=AccountImportStatus.NEEDS_MAPPING if needs_mapping else AccountImportStatus.READY_FOR_ANALYSIS,
        detected_report_type=detected_report_type,
        detection_confidence=detection_confidence,
        total_rows=total_rows,
        processed_rows=processed_rows,
        error_rows=error_rows,
        data_quality_warnings_json=warnings,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )


def _import_from_row(row: RowMapping) -> AccountImport:
    data = dict(row)
    if data.get("created_by") is not None:
        data["created_by"] = str(data["created_by"])
    data["data_quality_warnings_json"] = _json_loads(data.get("data_quality_warnings_json"), default=[])
    return AccountImport(**data)


def _entity_from_row(row: RowMapping) -> AccountImportEntity:
    data = dict(row)
    data["metrics_json"] = _json_loads(data.get("metrics_json"), default={})
    data["raw_row_refs_json"] = _json_loads(data.get("raw_row_refs_json"), default=[])
    return AccountImportEntity(**data)


def _suggestion_from_row(row: RowMapping) -> ProductMappingSuggestion:
    return ProductMappingSuggestion(**dict(row))


def _import_params(item: AccountImport) -> dict:
    return {
        **item.model_dump(),
        "report_type": item.report_type.value,
        "status": item.status.value,
        "detected_report_type": item.detected_report_type.value,
        "detection_confidence": item.detection_confidence.value,
        "created_by": _uuid_or_none(item.created_by),
        "data_quality_warnings_json": _json_dumps(item.data_quality_warnings_json),
    }


def _entity_params(item: AccountImportEntity) -> dict:
    return {
        **item.model_dump(),
        "entity_type": item.entity_type.value,
        "resolution_status": item.resolution_status.value,
        "metrics_json": _json_dumps(item.metrics_json),
        "raw_row_refs_json": _json_dumps(item.raw_row_refs_json),
    }


def _suggestion_params(item: ProductMappingSuggestion) -> dict:
    return {**item.model_dump(), "status": item.status.value}


def _uuid_or_none(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _json_dumps(value) -> str:
    import json

    return json.dumps(value, default=str)


def _json_loads(value, *, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    import json

    return json.loads(value)
