from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import UPLOAD_PARSER_VERSION
from apps.api.app.schemas.upload_parsing import (
    ParsedUploadRow,
    UploadParseError,
    UploadParseRun,
    UploadParseStatus,
)
from apps.api.app.schemas.uploads import UploadRecord


class UploadParsingRepository(ABC):
    @abstractmethod
    def create_run(self, *, upload: UploadRecord, job_id: UUID, detected_file_type: str) -> UploadParseRun:
        raise NotImplementedError

    @abstractmethod
    def complete_run(
        self,
        *,
        parse_run_id: UUID,
        status: UploadParseStatus,
        detected_file_type: str,
        detected_sheet_names: list[str],
        selected_sheet_name: str | None,
        total_rows: int,
        total_columns: int,
        parsed_rows_count: int,
        error_rows_count: int,
        error_message: str | None = None,
    ) -> UploadParseRun:
        raise NotImplementedError

    @abstractmethod
    def insert_rows(self, *, parse_run: UploadParseRun, rows: list[ParsedUploadRow]) -> None:
        raise NotImplementedError

    @abstractmethod
    def insert_errors(self, *, parse_run: UploadParseRun, errors: list[UploadParseError]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_runs(self, *, workspace_id: UUID, upload_id: UUID) -> list[UploadParseRun]:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, *, workspace_id: UUID, upload_id: UUID, parse_run_id: UUID) -> UploadParseRun | None:
        raise NotImplementedError

    @abstractmethod
    def list_rows(self, *, workspace_id: UUID, parse_run_id: UUID, page: int, page_size: int) -> tuple[list[ParsedUploadRow], int]:
        raise NotImplementedError

    @abstractmethod
    def list_errors(self, *, workspace_id: UUID, parse_run_id: UUID, page: int, page_size: int) -> tuple[list[UploadParseError], int]:
        raise NotImplementedError

    @abstractmethod
    def delete_by_upload(self, *, workspace_id: UUID, upload_id: UUID) -> None:
        raise NotImplementedError


class LocalUploadParsingRepository(UploadParsingRepository):
    def __init__(self) -> None:
        self._runs: dict[UUID, dict[UUID, UploadParseRun]] = {}
        self._rows: dict[UUID, list[ParsedUploadRow]] = {}
        self._errors: dict[UUID, list[UploadParseError]] = {}

    def create_run(self, *, upload: UploadRecord, job_id: UUID, detected_file_type: str) -> UploadParseRun:
        now = datetime.now(UTC)
        parse_run = UploadParseRun(
            id=uuid4(),
            workspace_id=upload.workspace_id,
            product_id=upload.product_id,
            upload_id=upload.id,
            job_id=job_id,
            status=UploadParseStatus.RUNNING,
            parser_version=UPLOAD_PARSER_VERSION,
            original_filename=upload.original_filename,
            storage_path=upload.storage_path,
            detected_file_type=detected_file_type,
            detected_sheet_names=[],
            selected_sheet_name=None,
            total_rows=0,
            total_columns=0,
            parsed_rows_count=0,
            error_rows_count=0,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
            error_message=None,
        )
        self._runs.setdefault(upload.workspace_id, {})[parse_run.id] = parse_run
        self._rows[parse_run.id] = []
        self._errors[parse_run.id] = []
        return parse_run

    def complete_run(
        self,
        *,
        parse_run_id: UUID,
        status: UploadParseStatus,
        detected_file_type: str,
        detected_sheet_names: list[str],
        selected_sheet_name: str | None,
        total_rows: int,
        total_columns: int,
        parsed_rows_count: int,
        error_rows_count: int,
        error_message: str | None = None,
    ) -> UploadParseRun:
        current = self._find_run(parse_run_id)
        now = datetime.now(UTC)
        updated = current.model_copy(
            update={
                "status": status,
                "detected_file_type": detected_file_type,
                "detected_sheet_names": detected_sheet_names,
                "selected_sheet_name": selected_sheet_name,
                "total_rows": total_rows,
                "total_columns": total_columns,
                "parsed_rows_count": parsed_rows_count,
                "error_rows_count": error_rows_count,
                "completed_at": now,
                "updated_at": now,
                "error_message": error_message,
            }
        )
        self._runs[updated.workspace_id][updated.id] = updated
        return updated

    def insert_rows(self, *, parse_run: UploadParseRun, rows: list[ParsedUploadRow]) -> None:
        now = datetime.now(UTC)
        self._rows[parse_run.id] = [
            row.model_copy(
                update={
                    "id": uuid4(),
                    "workspace_id": parse_run.workspace_id,
                    "product_id": parse_run.product_id,
                    "upload_id": parse_run.upload_id,
                    "parse_run_id": parse_run.id,
                    "created_at": now,
                }
            )
            for row in rows
        ]

    def insert_errors(self, *, parse_run: UploadParseRun, errors: list[UploadParseError]) -> None:
        now = datetime.now(UTC)
        self._errors[parse_run.id] = [
            error.model_copy(
                update={
                    "id": uuid4(),
                    "workspace_id": parse_run.workspace_id,
                    "product_id": parse_run.product_id,
                    "upload_id": parse_run.upload_id,
                    "parse_run_id": parse_run.id,
                    "created_at": now,
                }
            )
            for error in errors
        ]

    def list_runs(self, *, workspace_id: UUID, upload_id: UUID) -> list[UploadParseRun]:
        runs = [run for run in self._runs.get(workspace_id, {}).values() if run.upload_id == upload_id]
        return sorted(runs, key=lambda run: run.created_at, reverse=True)

    def get_run(self, *, workspace_id: UUID, upload_id: UUID, parse_run_id: UUID) -> UploadParseRun | None:
        run = self._runs.get(workspace_id, {}).get(parse_run_id)
        return run if run and run.upload_id == upload_id else None

    def list_rows(self, *, workspace_id: UUID, parse_run_id: UUID, page: int, page_size: int) -> tuple[list[ParsedUploadRow], int]:
        run = self._runs.get(workspace_id, {}).get(parse_run_id)
        rows = self._rows.get(parse_run_id, []) if run else []
        return _paginate(rows, page, page_size)

    def list_errors(self, *, workspace_id: UUID, parse_run_id: UUID, page: int, page_size: int) -> tuple[list[UploadParseError], int]:
        run = self._runs.get(workspace_id, {}).get(parse_run_id)
        errors = self._errors.get(parse_run_id, []) if run else []
        return _paginate(errors, page, page_size)

    def delete_by_upload(self, *, workspace_id: UUID, upload_id: UUID) -> None:
        runs = self._runs.get(workspace_id, {})
        parse_run_ids = [run_id for run_id, run in runs.items() if run.upload_id == upload_id]
        for parse_run_id in parse_run_ids:
            self._rows.pop(parse_run_id, None)
            self._errors.pop(parse_run_id, None)
            runs.pop(parse_run_id, None)

    def _find_run(self, parse_run_id: UUID) -> UploadParseRun:
        for runs in self._runs.values():
            if parse_run_id in runs:
                return runs[parse_run_id]
        raise ApiError(code="PARSE_RUN_NOT_FOUND", message="Parse run was not found.", status_code=404)


class PostgresUploadParsingRepository(UploadParsingRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_run(self, *, upload: UploadRecord, job_id: UUID, detected_file_type: str) -> UploadParseRun:
        now = datetime.now(UTC).isoformat()
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into upload_parse_runs (
                        id, workspace_id, product_id, upload_id, job_id, status, parser_version,
                        original_filename, storage_path, detected_file_type, started_at, created_at, updated_at
                    )
                    values (
                        :id, :workspace_id, :product_id, :upload_id, :job_id, 'running', :parser_version,
                        :original_filename, :storage_path, :detected_file_type, :started_at, :created_at, :updated_at
                    )
                    returning *
                    """
                ),
                {
                    "id": uuid4(),
                    "workspace_id": upload.workspace_id,
                    "product_id": upload.product_id,
                    "upload_id": upload.id,
                    "job_id": job_id,
                    "parser_version": UPLOAD_PARSER_VERSION,
                    "original_filename": upload.original_filename,
                    "storage_path": upload.storage_path,
                    "detected_file_type": detected_file_type,
                    "started_at": now,
                    "created_at": now,
                    "updated_at": now,
                },
            ).mappings().one()
        return _run_from_row(row)

    def complete_run(
        self,
        *,
        parse_run_id: UUID,
        status: UploadParseStatus,
        detected_file_type: str,
        detected_sheet_names: list[str],
        selected_sheet_name: str | None,
        total_rows: int,
        total_columns: int,
        parsed_rows_count: int,
        error_rows_count: int,
        error_message: str | None = None,
    ) -> UploadParseRun:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update upload_parse_runs
                    set status = :status,
                        detected_file_type = :detected_file_type,
                        detected_sheet_names = :detected_sheet_names,
                        selected_sheet_name = :selected_sheet_name,
                        total_rows = :total_rows,
                        total_columns = :total_columns,
                        parsed_rows_count = :parsed_rows_count,
                        error_rows_count = :error_rows_count,
                        completed_at = datetime('now'),
                        updated_at = datetime('now'),
                        error_message = :error_message
                    where id = :parse_run_id
                    returning *
                    """
                ),
                {
                    "parse_run_id": parse_run_id,
                    "status": status.value,
                    "detected_file_type": detected_file_type,
                    "detected_sheet_names": _json_dumps(detected_sheet_names),
                    "selected_sheet_name": selected_sheet_name,
                    "total_rows": total_rows,
                    "total_columns": total_columns,
                    "parsed_rows_count": parsed_rows_count,
                    "error_rows_count": error_rows_count,
                    "error_message": error_message,
                },
            ).mappings().one()
        return _run_from_row(row)

    def insert_rows(self, *, parse_run: UploadParseRun, rows: list[ParsedUploadRow]) -> None:
        if not rows:
            return
        now = datetime.now(UTC).isoformat()
        statement = text(
            """
            insert into upload_parsed_rows (
                id, workspace_id, product_id, upload_id, parse_run_id, row_number,
                row_data_json, row_hash, created_at
            )
            values (
                :id, :workspace_id, :product_id, :upload_id, :parse_run_id, :row_number,
                :row_data_json, :row_hash, :created_at
            )
            """
        )
        params = [_row_params(parse_run, row, created_at=now) for row in rows]
        with self._engine.begin() as connection:
            connection.execute(statement, params)

    def insert_errors(self, *, parse_run: UploadParseRun, errors: list[UploadParseError]) -> None:
        if not errors:
            return
        now = datetime.now(UTC).isoformat()
        statement = text(
            """
            insert into upload_parse_errors (
                id, workspace_id, product_id, upload_id, parse_run_id, row_number,
                error_code, error_message, raw_value_json, created_at
            )
            values (
                :id, :workspace_id, :product_id, :upload_id, :parse_run_id, :row_number,
                :error_code, :error_message, :raw_value_json, :created_at
            )
            """
        )
        params = [_error_params(parse_run, error, created_at=now) for error in errors]
        with self._engine.begin() as connection:
            connection.execute(statement, params)

    def list_runs(self, *, workspace_id: UUID, upload_id: UUID) -> list[UploadParseRun]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text("select * from upload_parse_runs where workspace_id = :workspace_id and upload_id = :upload_id order by created_at desc"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            ).mappings().all()
        return [_run_from_row(row) for row in rows]

    def get_run(self, *, workspace_id: UUID, upload_id: UUID, parse_run_id: UUID) -> UploadParseRun | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    select * from upload_parse_runs
                    where workspace_id = :workspace_id and upload_id = :upload_id and id = :parse_run_id
                    """
                ),
                {"workspace_id": workspace_id, "upload_id": upload_id, "parse_run_id": parse_run_id},
            ).mappings().first()
        return _run_from_row(row) if row else None

    def list_rows(self, *, workspace_id: UUID, parse_run_id: UUID, page: int, page_size: int) -> tuple[list[ParsedUploadRow], int]:
        return self._list_child_records(
            table="upload_parsed_rows",
            mapper=_parsed_row_from_row,
            workspace_id=workspace_id,
            parse_run_id=parse_run_id,
            page=page,
            page_size=page_size,
        )

    def list_errors(self, *, workspace_id: UUID, parse_run_id: UUID, page: int, page_size: int) -> tuple[list[UploadParseError], int]:
        return self._list_child_records(
            table="upload_parse_errors",
            mapper=_parse_error_from_row,
            workspace_id=workspace_id,
            parse_run_id=parse_run_id,
            page=page,
            page_size=page_size,
        )

    def delete_by_upload(self, *, workspace_id: UUID, upload_id: UUID) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("delete from upload_column_profile_columns where workspace_id = :workspace_id and upload_id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            )
            connection.execute(
                text("delete from upload_column_mappings where workspace_id = :workspace_id and upload_id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            )
            connection.execute(
                text("delete from upload_column_profiles where workspace_id = :workspace_id and upload_id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            )
            connection.execute(
                text("delete from upload_parsed_rows where workspace_id = :workspace_id and upload_id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            )
            connection.execute(
                text("delete from upload_parse_errors where workspace_id = :workspace_id and upload_id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            )
            connection.execute(
                text("delete from upload_parse_runs where workspace_id = :workspace_id and upload_id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            )

    def _list_child_records(self, *, table: str, mapper, workspace_id: UUID, parse_run_id: UUID, page: int, page_size: int):
        params = {"workspace_id": workspace_id, "parse_run_id": parse_run_id, "limit": page_size, "offset": (page - 1) * page_size}
        with self._engine.begin() as connection:
            total = connection.execute(
                text(f"select count(*) from {table} where workspace_id = :workspace_id and parse_run_id = :parse_run_id"),
                params,
            ).scalar_one()
            rows = connection.execute(
                text(
                    f"""
                    select * from {table}
                    where workspace_id = :workspace_id and parse_run_id = :parse_run_id
                    order by row_number asc nulls first, created_at asc
                    limit :limit offset :offset
                    """
                ),
                params,
            ).mappings().all()
        return [mapper(row) for row in rows], int(total)


_local_repository = LocalUploadParsingRepository()


def get_upload_parsing_repository() -> UploadParsingRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresUploadParsingRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def _paginate(items: list, page: int, page_size: int):
    start = (page - 1) * page_size
    return items[start : start + page_size], len(items)


def _run_from_row(row: RowMapping) -> UploadParseRun:
    return UploadParseRun(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        upload_id=row["upload_id"],
        job_id=row["job_id"],
        status=row["status"],
        parser_version=row["parser_version"],
        original_filename=row["original_filename"],
        storage_path=row["storage_path"],
        detected_file_type=row["detected_file_type"],
        detected_sheet_names=_json_loads(row["detected_sheet_names"], default=[]),
        selected_sheet_name=row["selected_sheet_name"],
        total_rows=row["total_rows"],
        total_columns=row["total_columns"],
        parsed_rows_count=row["parsed_rows_count"],
        error_rows_count=row["error_rows_count"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error_message=row["error_message"],
    )


def _parsed_row_from_row(row: RowMapping) -> ParsedUploadRow:
    return ParsedUploadRow(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        upload_id=row["upload_id"],
        parse_run_id=row["parse_run_id"],
        row_number=row["row_number"],
        row_data_json=_json_loads(row["row_data_json"], default={}),
        row_hash=row["row_hash"],
        created_at=row["created_at"],
    )


def _parse_error_from_row(row: RowMapping) -> UploadParseError:
    return UploadParseError(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        upload_id=row["upload_id"],
        parse_run_id=row["parse_run_id"],
        row_number=row["row_number"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        raw_value_json=_json_loads(row["raw_value_json"], default=None),
        created_at=row["created_at"],
    )


def _row_params(parse_run: UploadParseRun, row: ParsedUploadRow, *, created_at: str) -> dict:
    return {
        "id": uuid4(),
        "workspace_id": parse_run.workspace_id,
        "product_id": parse_run.product_id,
        "upload_id": parse_run.upload_id,
        "parse_run_id": parse_run.id,
        "row_number": row.row_number,
        "row_data_json": _json_dumps(row.row_data_json),
        "row_hash": row.row_hash,
        "created_at": created_at,
    }


def _error_params(parse_run: UploadParseRun, error: UploadParseError, *, created_at: str) -> dict:
    return {
        "id": uuid4(),
        "workspace_id": parse_run.workspace_id,
        "product_id": parse_run.product_id,
        "upload_id": parse_run.upload_id,
        "parse_run_id": parse_run.id,
        "row_number": error.row_number,
        "error_code": error.error_code,
        "error_message": error.error_message,
        "raw_value_json": _json_dumps(error.raw_value_json),
        "created_at": created_at,
    }


def _json_dumps(value) -> str:
    import json

    return json.dumps(value)


def _json_loads(value, *, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    import json

    return json.loads(value)
