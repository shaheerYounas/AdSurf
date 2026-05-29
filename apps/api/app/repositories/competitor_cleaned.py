from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.competitor_cleaned import (
    CompetitorCleanedRow,
    CompetitorUpload,
    CompetitorUploadStatus,
)


class CompetitorCleanedRepository(ABC):
    @abstractmethod
    def create_upload(
        self, *, upload_id: UUID, workspace_id: UUID, product_id: UUID | None,
        original_filename: str, storage_path: str, mime_type: str,
        file_size_bytes: int, uploaded_by: str,
    ) -> CompetitorUpload:
        raise NotImplementedError

    @abstractmethod
    def get_upload(self, *, workspace_id: UUID, upload_id: UUID) -> CompetitorUpload | None:
        raise NotImplementedError

    @abstractmethod
    def list_uploads(
        self, *, workspace_id: UUID, product_id: UUID | None = None,
        page: int = 1, page_size: int = 20,
    ) -> tuple[list[CompetitorUpload], int]:
        raise NotImplementedError

    @abstractmethod
    def update_upload_status(
        self, *, workspace_id: UUID, upload_id: UUID, status: CompetitorUploadStatus,
        row_count: int | None = None, cleaned_column_count: int | None = None,
        detected_columns_json: list[dict] | None = None,
        warnings_json: list[dict] | None = None,
        error_message: str | None = None,
    ) -> CompetitorUpload:
        raise NotImplementedError

    @abstractmethod
    def insert_rows(self, *, rows: list[CompetitorCleanedRow]) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_rows(
        self, *, workspace_id: UUID, competitor_upload_id: UUID,
        page: int = 1, page_size: int = 20,
    ) -> tuple[list[CompetitorCleanedRow], int]:
        raise NotImplementedError

    @abstractmethod
    def update_scored_rows(self, *, rows: list[CompetitorCleanedRow]) -> int:
        raise NotImplementedError

    @abstractmethod
    def update_verification_rows(self, *, rows: list[CompetitorCleanedRow]) -> int:
        raise NotImplementedError


class LocalCompetitorCleanedRepository(CompetitorCleanedRepository):
    def __init__(self) -> None:
        self._uploads: dict[UUID, CompetitorUpload] = {}
        self._rows: dict[UUID, list[CompetitorCleanedRow]] = {}

    def create_upload(self, *, upload_id: UUID, workspace_id: UUID, product_id: UUID | None, original_filename: str, storage_path: str, mime_type: str, file_size_bytes: int, uploaded_by: str) -> CompetitorUpload:
        now = datetime.now(UTC)
        upload = CompetitorUpload(
            id=upload_id, workspace_id=workspace_id, product_id=product_id,
            original_filename=original_filename, storage_path=storage_path,
            mime_type=mime_type, file_size_bytes=file_size_bytes,
            status=CompetitorUploadStatus.QUEUED, uploaded_by=uploaded_by,
            created_at=now, updated_at=now,
        )
        self._uploads[upload.id] = upload
        self._rows[upload.id] = []
        return upload

    def get_upload(self, *, workspace_id: UUID, upload_id: UUID) -> CompetitorUpload | None:
        upload = self._uploads.get(upload_id)
        return upload if upload and upload.workspace_id == workspace_id else None

    def list_uploads(self, *, workspace_id: UUID, product_id: UUID | None = None, page: int = 1, page_size: int = 20) -> tuple[list[CompetitorUpload], int]:
        filtered = [upload for upload in self._uploads.values() if upload.workspace_id == workspace_id]
        if product_id:
            filtered = [upload for upload in filtered if upload.product_id == product_id]
        filtered.sort(key=lambda upload: upload.created_at, reverse=True)
        total = len(filtered)
        start = (page - 1) * page_size
        return filtered[start:start + page_size], total

    def update_upload_status(self, *, workspace_id: UUID, upload_id: UUID, status: CompetitorUploadStatus, row_count: int | None = None, cleaned_column_count: int | None = None, detected_columns_json: list[dict] | None = None, warnings_json: list[dict] | None = None, error_message: str | None = None) -> CompetitorUpload:
        upload = self._uploads.get(upload_id)
        if not upload or upload.workspace_id != workspace_id:
            raise ApiError(code="COMPETITOR_UPLOAD_NOT_FOUND", message="Competitor upload was not found.", status_code=404)
        now = datetime.now(UTC)
        updated = upload.model_copy(update={
            "status": status, "updated_at": now,
            "row_count": row_count if row_count is not None else upload.row_count,
            "cleaned_column_count": cleaned_column_count if cleaned_column_count is not None else upload.cleaned_column_count,
            "detected_columns_json": detected_columns_json if detected_columns_json is not None else upload.detected_columns_json,
            "warnings_json": warnings_json if warnings_json is not None else upload.warnings_json,
            "error_message": error_message if error_message is not None else upload.error_message,
        })
        self._uploads[upload_id] = updated
        return updated

    def insert_rows(self, *, rows: list[CompetitorCleanedRow]) -> int:
        for row in rows:
            key = row.competitor_upload_id
            if key not in self._rows:
                self._rows[key] = []
            self._rows[key].append(row)
        return len(rows)

    def list_rows(self, *, workspace_id: UUID, competitor_upload_id: UUID, page: int = 1, page_size: int = 20) -> tuple[list[CompetitorCleanedRow], int]:
        rows = [r for r in self._rows.get(competitor_upload_id, []) if r.workspace_id == workspace_id]
        rows.sort(key=lambda r: r.row_number)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start:start + page_size], total

    def update_scored_rows(self, *, rows: list[CompetitorCleanedRow]) -> int:
        for row in rows:
            key = row.competitor_upload_id
            if key in self._rows:
                for idx, existing in enumerate(self._rows[key]):
                    if existing.id == row.id:
                        self._rows[key][idx] = row
                        break
        return len(rows)

    def update_verification_rows(self, *, rows: list[CompetitorCleanedRow]) -> int:
        for row in rows:
            key = row.competitor_upload_id
            if key in self._rows:
                for idx, existing in enumerate(self._rows[key]):
                    if existing.id == row.id:
                        self._rows[key][idx] = row
                        break
        return len(rows)


class PostgresCompetitorCleanedRepository(CompetitorCleanedRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_upload(self, *, upload_id: UUID, workspace_id: UUID, product_id: UUID | None, original_filename: str, storage_path: str, mime_type: str, file_size_bytes: int, uploaded_by: str) -> CompetitorUpload:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into competitor_uploads (
                        id, workspace_id, product_id, original_filename, storage_path,
                        mime_type, file_size_bytes, status, uploaded_by
                    ) values (
                        :id, :workspace_id, :product_id, :original_filename, :storage_path,
                        :mime_type, :file_size_bytes, 'queued', :uploaded_by
                    )
                    returning *
                    """
                ),
                {
                    "id": upload_id, "workspace_id": workspace_id,
                    "product_id": product_id, "original_filename": original_filename,
                    "storage_path": storage_path, "mime_type": mime_type,
                    "file_size_bytes": file_size_bytes, "uploaded_by": uploaded_by,
                },
            ).mappings().one()
        return _upload_from_row(row)

    def get_upload(self, *, workspace_id: UUID, upload_id: UUID) -> CompetitorUpload | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from competitor_uploads where workspace_id = :workspace_id and id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            ).mappings().first()
        return _upload_from_row(row) if row else None

    def list_uploads(self, *, workspace_id: UUID, product_id: UUID | None = None, page: int = 1, page_size: int = 20) -> tuple[list[CompetitorUpload], int]:
        conditions = ["workspace_id = :workspace_id"]
        params: dict[str, object] = {"workspace_id": workspace_id, "limit": page_size, "offset": (page - 1) * page_size}
        if product_id:
            conditions.append("product_id = :product_id")
            params["product_id"] = product_id
        where_clause = " and ".join(conditions)
        with self._engine.begin() as connection:
            total = connection.execute(text(f"select count(*) from competitor_uploads where {where_clause}"), params).scalar_one()
            rows = connection.execute(
                text(f"select * from competitor_uploads where {where_clause} order by created_at desc limit :limit offset :offset"),
                params,
            ).mappings().all()
        return [_upload_from_row(row) for row in rows], int(total)

    def update_upload_status(self, *, workspace_id: UUID, upload_id: UUID, status: CompetitorUploadStatus, row_count: int | None = None, cleaned_column_count: int | None = None, detected_columns_json: list[dict] | None = None, warnings_json: list[dict] | None = None, error_message: str | None = None) -> CompetitorUpload:
        import json
        sets = ["status = :status", "updated_at = now()"]
        params: dict[str, object] = {"workspace_id": workspace_id, "upload_id": upload_id, "status": status.value}
        if row_count is not None:
            sets.append("row_count = :row_count")
            params["row_count"] = row_count
        if cleaned_column_count is not None:
            sets.append("cleaned_column_count = :cleaned_column_count")
            params["cleaned_column_count"] = cleaned_column_count
        if detected_columns_json is not None:
            sets.append("detected_columns_json = cast(:detected_columns_json as jsonb)")
            params["detected_columns_json"] = json.dumps(detected_columns_json)
        if warnings_json is not None:
            sets.append("warnings_json = cast(:warnings_json as jsonb)")
            params["warnings_json"] = json.dumps(warnings_json)
        if error_message is not None:
            sets.append("error_message = :error_message")
            params["error_message"] = error_message
        with self._engine.begin() as connection:
            row = connection.execute(
                text(f"update competitor_uploads set {', '.join(sets)} where workspace_id = :workspace_id and id = :upload_id returning *"),
                params,
            ).mappings().one()
        return _upload_from_row(row)

    def insert_rows(self, *, rows: list[CompetitorCleanedRow]) -> int:
        if not rows:
            return 0
        import json
        with self._engine.begin() as connection:
            for row in rows:
                connection.execute(
                    text(
                        """
                        insert into competitor_cleaned_rows (
                            id, workspace_id, competitor_upload_id, row_number,
                            search_term, search_volume, competitor_rank_values_json,
                            raw_metrics_json
                        ) values (
                            :id, :workspace_id, :competitor_upload_id, :row_number,
                            :search_term, :search_volume, cast(:competitor_rank_values_json as jsonb),
                            cast(:raw_metrics_json as jsonb)
                        )
                        """
                    ),
                    {
                        "id": row.id or uuid4(),
                        "workspace_id": row.workspace_id,
                        "competitor_upload_id": row.competitor_upload_id,
                        "row_number": row.row_number,
                        "search_term": row.search_term,
                        "search_volume": str(row.search_volume) if row.search_volume is not None else None,
                        "competitor_rank_values_json": json.dumps(row.competitor_rank_values_json),
                        "raw_metrics_json": json.dumps(row.raw_metrics_json) if row.raw_metrics_json else None,
                    },
                )
        return len(rows)

    def list_rows(self, *, workspace_id: UUID, competitor_upload_id: UUID, page: int = 1, page_size: int = 20) -> tuple[list[CompetitorCleanedRow], int]:
        params: dict[str, object] = {
            "workspace_id": workspace_id, "competitor_upload_id": competitor_upload_id,
            "limit": page_size, "offset": (page - 1) * page_size,
        }
        with self._engine.begin() as connection:
            total = connection.execute(
                text("select count(*) from competitor_cleaned_rows where workspace_id = :workspace_id and competitor_upload_id = :competitor_upload_id"),
                params,
            ).scalar_one()
            rows = connection.execute(
                text("select * from competitor_cleaned_rows where workspace_id = :workspace_id and competitor_upload_id = :competitor_upload_id order by row_number limit :limit offset :offset"),
                params,
            ).mappings().all()
        return [_cleaned_row_from_row(row) for row in rows], int(total)

    def update_scored_rows(self, *, rows: list[CompetitorCleanedRow]) -> int:
        if not rows:
            return 0
        with self._engine.begin() as connection:
            for row in rows:
                connection.execute(
                    text(
                        """
                        update competitor_cleaned_rows
                        set relevance_score = :relevance_score,
                            scoring_status = :scoring_status,
                            rejection_reason = :rejection_reason,
                            scored_at = now()
                        where id = :id
                        """
                    ),
                    {
                        "id": row.id,
                        "relevance_score": row.relevance_score,
                        "scoring_status": row.scoring_status,
                        "rejection_reason": row.rejection_reason,
                    },
                )
        return len(rows)

    def update_verification_rows(self, *, rows: list[CompetitorCleanedRow]) -> int:
        if not rows:
            return 0
        import json
        with self._engine.begin() as connection:
            for row in rows:
                connection.execute(
                    text(
                        """
                        update competitor_cleaned_rows
                        set verification_status = :verification_status,
                            verification_result_json = cast(:verification_result_json as jsonb),
                            verified_at = now()
                        where id = :id
                        """
                    ),
                    {
                        "id": row.id,
                        "verification_status": row.verification_status,
                        "verification_result_json": json.dumps(row.verification_result_json) if row.verification_result_json else None,
                    },
                )
        return len(rows)


_local_repository = LocalCompetitorCleanedRepository()


def get_competitor_cleaned_repository() -> CompetitorCleanedRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresCompetitorCleanedRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def _upload_from_row(row: RowMapping) -> CompetitorUpload:
    return CompetitorUpload(
        id=row["id"], workspace_id=row["workspace_id"], product_id=row["product_id"],
        original_filename=row["original_filename"], storage_path=row["storage_path"],
        mime_type=row["mime_type"], file_size_bytes=row["file_size_bytes"],
        status=row["status"], row_count=row["row_count"],
        cleaned_column_count=row["cleaned_column_count"],
        detected_columns_json=row["detected_columns_json"] or [],
        warnings_json=row["warnings_json"] or [],
        error_message=row["error_message"], uploaded_by=row["uploaded_by"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _cleaned_row_from_row(row: RowMapping) -> CompetitorCleanedRow:
    search_volume = row["search_volume"]
    return CompetitorCleanedRow(
        id=row["id"], workspace_id=row["workspace_id"],
        competitor_upload_id=row["competitor_upload_id"],
        row_number=row["row_number"], search_term=row["search_term"],
        search_volume=float(search_volume) if search_volume is not None else None,
        competitor_rank_values_json=row["competitor_rank_values_json"] or [],
        raw_metrics_json=row["raw_metrics_json"],
        relevance_score=row["relevance_score"] if "relevance_score" in row else None,
        scoring_status=row["scoring_status"] if "scoring_status" in row else None,
        rejection_reason=row["rejection_reason"] if "rejection_reason" in row else None,
        scored_at=row["scored_at"] if "scored_at" in row else None,
        verification_status=row["verification_status"] if "verification_status" in row else None,
        verification_result_json=row["verification_result_json"] if "verification_result_json" in row else None,
        verified_at=row["verified_at"] if "verified_at" in row else None,
        created_at=row["created_at"],
    )
