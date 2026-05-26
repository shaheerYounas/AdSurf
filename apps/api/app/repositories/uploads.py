from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.uploads import UploadInitRequest, UploadRecord, UploadStatus


class UploadRepository(ABC):
    @abstractmethod
    def create_initialized(
        self,
        *,
        upload_id: UUID,
        workspace_id: UUID,
        product_id: UUID,
        payload: UploadInitRequest,
        storage_path: str,
        actor_user_id: str,
        idempotency_key: str,
    ) -> UploadRecord:
        raise NotImplementedError

    @abstractmethod
    def get_by_idempotency_key(self, *, workspace_id: UUID, idempotency_key: str) -> UploadRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get(self, *, workspace_id: UUID, upload_id: UUID) -> UploadRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list(
        self,
        *,
        workspace_id: UUID,
        product_id: UUID | None,
        status: UploadStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[UploadRecord], int]:
        raise NotImplementedError

    @abstractmethod
    def mark_queued_for_processing(self, *, workspace_id: UUID, upload_id: UUID) -> UploadRecord | None:
        raise NotImplementedError

    @abstractmethod
    def update_status(self, *, workspace_id: UUID, upload_id: UUID, status: UploadStatus) -> UploadRecord | None:
        raise NotImplementedError


class LocalUploadRepository(UploadRepository):
    """Local/test repository used only when DATABASE_URL is absent in local/test."""

    def __init__(self) -> None:
        self._uploads: dict[UUID, dict[UUID, UploadRecord]] = {}

    def create_initialized(
        self,
        *,
        upload_id: UUID,
        workspace_id: UUID,
        product_id: UUID,
        payload: UploadInitRequest,
        storage_path: str,
        actor_user_id: str,
        idempotency_key: str,
    ) -> UploadRecord:
        existing = self.get_by_idempotency_key(workspace_id=workspace_id, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        upload = UploadRecord(
            id=upload_id,
            workspace_id=workspace_id,
            product_id=product_id,
            uploaded_by=actor_user_id,
            original_filename=payload.original_filename,
            storage_path=storage_path,
            mime_type=payload.mime_type,
            file_size_bytes=payload.file_size_bytes,
            status=UploadStatus.INITIALIZED,
            source_type=payload.source_type,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
            confirmed_at=None,
        )
        self._uploads.setdefault(workspace_id, {})[upload.id] = upload
        return upload

    def get_by_idempotency_key(self, *, workspace_id: UUID, idempotency_key: str) -> UploadRecord | None:
        for upload in self._uploads.get(workspace_id, {}).values():
            if upload.idempotency_key == idempotency_key:
                return upload
        return None

    def get(self, *, workspace_id: UUID, upload_id: UUID) -> UploadRecord | None:
        return self._uploads.get(workspace_id, {}).get(upload_id)

    def list(
        self,
        *,
        workspace_id: UUID,
        product_id: UUID | None,
        status: UploadStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[UploadRecord], int]:
        uploads = list(self._uploads.get(workspace_id, {}).values())
        if product_id is not None:
            uploads = [upload for upload in uploads if upload.product_id == product_id]
        if status is not None:
            uploads = [upload for upload in uploads if upload.status == status]
        uploads.sort(key=lambda upload: upload.created_at, reverse=True)
        total = len(uploads)
        start = (page - 1) * page_size
        return uploads[start : start + page_size], total

    def mark_queued_for_processing(self, *, workspace_id: UUID, upload_id: UUID) -> UploadRecord | None:
        current = self.get(workspace_id=workspace_id, upload_id=upload_id)
        if current is None:
            return None
        if current.status != UploadStatus.INITIALIZED:
            return current
        updated = current.model_copy(
            update={
                "status": UploadStatus.QUEUED_FOR_PROCESSING,
                "confirmed_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        self._uploads[workspace_id][upload_id] = updated
        return updated

    def update_status(self, *, workspace_id: UUID, upload_id: UUID, status: UploadStatus) -> UploadRecord | None:
        current = self.get(workspace_id=workspace_id, upload_id=upload_id)
        if current is None:
            return None
        updated = current.model_copy(update={"status": status, "updated_at": datetime.now(UTC)})
        self._uploads[workspace_id][upload_id] = updated
        return updated


class PostgresUploadRepository(UploadRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_initialized(
        self,
        *,
        upload_id: UUID,
        workspace_id: UUID,
        product_id: UUID,
        payload: UploadInitRequest,
        storage_path: str,
        actor_user_id: str,
        idempotency_key: str,
    ) -> UploadRecord:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into uploads (
                        id, workspace_id, product_id, uploaded_by, original_filename, storage_path,
                        mime_type, file_size_bytes, status, source_type, idempotency_key
                    )
                    values (
                        :id, :workspace_id, :product_id, :uploaded_by, :original_filename, :storage_path,
                        :mime_type, :file_size_bytes, 'initialized', :source_type, :idempotency_key
                    )
                    on conflict (workspace_id, idempotency_key) do update
                    set updated_at = uploads.updated_at
                    returning id, workspace_id, product_id, uploaded_by, original_filename, storage_path,
                        mime_type, file_size_bytes, status, source_type, idempotency_key, created_at,
                        updated_at, confirmed_at
                    """
                ),
                {
                    "id": upload_id,
                    "workspace_id": workspace_id,
                    "product_id": product_id,
                    "uploaded_by": _uuid_or_none(actor_user_id),
                    "original_filename": payload.original_filename,
                    "storage_path": storage_path,
                    "mime_type": payload.mime_type,
                    "file_size_bytes": payload.file_size_bytes,
                    "source_type": payload.source_type,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().one()
        return _upload_from_row(row)

    def get_by_idempotency_key(self, *, workspace_id: UUID, idempotency_key: str) -> UploadRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    select id, workspace_id, product_id, uploaded_by, original_filename, storage_path,
                        mime_type, file_size_bytes, status, source_type, idempotency_key, created_at,
                        updated_at, confirmed_at
                    from uploads
                    where workspace_id = :workspace_id and idempotency_key = :idempotency_key
                    """
                ),
                {"workspace_id": workspace_id, "idempotency_key": idempotency_key},
            ).mappings().first()
        return _upload_from_row(row) if row else None

    def get(self, *, workspace_id: UUID, upload_id: UUID) -> UploadRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    select id, workspace_id, product_id, uploaded_by, original_filename, storage_path,
                        mime_type, file_size_bytes, status, source_type, idempotency_key, created_at,
                        updated_at, confirmed_at
                    from uploads
                    where workspace_id = :workspace_id and id = :upload_id
                    """
                ),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            ).mappings().first()
        return _upload_from_row(row) if row else None

    def list(
        self,
        *,
        workspace_id: UUID,
        product_id: UUID | None,
        status: UploadStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[UploadRecord], int]:
        clauses = ["workspace_id = :workspace_id"]
        params: dict[str, object] = {"workspace_id": workspace_id, "limit": page_size, "offset": (page - 1) * page_size}
        if product_id is not None:
            clauses.append("product_id = :product_id")
            params["product_id"] = product_id
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status.value
        where_clause = " and ".join(clauses)
        with self._engine.begin() as connection:
            total = connection.execute(
                text(f"select count(*) from uploads where {where_clause}"),
                params,
            ).scalar_one()
            rows = connection.execute(
                text(
                    f"""
                    select id, workspace_id, product_id, uploaded_by, original_filename, storage_path,
                        mime_type, file_size_bytes, status, source_type, idempotency_key, created_at,
                        updated_at, confirmed_at
                    from uploads
                    where {where_clause}
                    order by created_at desc
                    limit :limit offset :offset
                    """
                ),
                params,
            ).mappings().all()
        return [_upload_from_row(row) for row in rows], int(total)

    def mark_queued_for_processing(self, *, workspace_id: UUID, upload_id: UUID) -> UploadRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update uploads
                    set status = case when status = 'initialized' then 'queued_for_processing' else status end,
                        confirmed_at = case when status = 'initialized' then now() else confirmed_at end,
                        updated_at = now()
                    where workspace_id = :workspace_id and id = :upload_id
                    returning id, workspace_id, product_id, uploaded_by, original_filename, storage_path,
                        mime_type, file_size_bytes, status, source_type, idempotency_key, created_at,
                        updated_at, confirmed_at
                    """
                ),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            ).mappings().first()
        return _upload_from_row(row) if row else None

    def update_status(self, *, workspace_id: UUID, upload_id: UUID, status: UploadStatus) -> UploadRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update uploads
                    set status = :status,
                        updated_at = now()
                    where workspace_id = :workspace_id and id = :upload_id
                    returning id, workspace_id, product_id, uploaded_by, original_filename, storage_path,
                        mime_type, file_size_bytes, status, source_type, idempotency_key, created_at,
                        updated_at, confirmed_at
                    """
                ),
                {"workspace_id": workspace_id, "upload_id": upload_id, "status": status.value},
            ).mappings().first()
        return _upload_from_row(row) if row else None


_local_repository = LocalUploadRepository()


def get_upload_repository() -> UploadRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresUploadRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def _upload_from_row(row: RowMapping) -> UploadRecord:
    return UploadRecord(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        uploaded_by=str(row["uploaded_by"]) if row["uploaded_by"] is not None else None,
        original_filename=row["original_filename"],
        storage_path=row["storage_path"],
        mime_type=row["mime_type"],
        file_size_bytes=row["file_size_bytes"],
        status=row["status"],
        source_type=row["source_type"],
        idempotency_key=row["idempotency_key"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        confirmed_at=row["confirmed_at"],
    )


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
