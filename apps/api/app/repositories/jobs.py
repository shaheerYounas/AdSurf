from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import PROCESS_UPLOAD_JOB_TYPE
from apps.api.app.schemas.jobs import JobRecord, JobStatus
from apps.api.app.schemas.uploads import UploadRecord


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class JobRepository(ABC):
    @abstractmethod
    def enqueue_process_upload(self, *, upload: UploadRecord) -> tuple[JobRecord, bool]:
        raise NotImplementedError

    @abstractmethod
    def enqueue_process_monitoring_import(
        self,
        *,
        workspace_id: UUID,
        product_id: UUID,
        monitoring_import_id: UUID,
        upload_id: UUID,
        parse_run_id: UUID,
    ) -> tuple[JobRecord, bool]:
        raise NotImplementedError

    @abstractmethod
    def get(self, *, workspace_id: UUID, job_id: UUID) -> JobRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_process_upload_job(self, *, workspace_id: UUID, upload_id: UUID) -> JobRecord | None:
        raise NotImplementedError

    @abstractmethod
    def claim_next(self, *, job_type: str, worker_id: str) -> JobRecord | None:
        raise NotImplementedError

    @abstractmethod
    def update_status(self, *, workspace_id: UUID, job_id: UUID, status: JobStatus, last_error: str | None = None) -> JobRecord | None:
        raise NotImplementedError

    @abstractmethod
    def delete_upload_jobs(self, *, workspace_id: UUID, upload_id: UUID) -> int:
        raise NotImplementedError

    @abstractmethod
    def clear_queued_jobs(self, *, job_type: str | None = None) -> int:
        raise NotImplementedError


class LocalJobRepository(JobRepository):
    """Local/test repository used only when DATABASE_URL is absent in local/test."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, dict[UUID, JobRecord]] = {}

    def enqueue_process_upload(self, *, upload: UploadRecord) -> tuple[JobRecord, bool]:
        existing = self.get_process_upload_job(workspace_id=upload.workspace_id, upload_id=upload.id)
        if existing is not None:
            return existing, False
        now = datetime.now(UTC)
        job = JobRecord(
            id=uuid4(),
            workspace_id=upload.workspace_id,
            job_type=PROCESS_UPLOAD_JOB_TYPE,
            status=JobStatus.QUEUED,
            payload_json=_process_upload_payload(upload),
            idempotency_key=_process_upload_idempotency_key(upload.id),
            created_at=now,
            updated_at=now,
        )
        self._jobs.setdefault(upload.workspace_id, {})[job.id] = job
        return job, True

    def enqueue_process_monitoring_import(
        self,
        *,
        workspace_id: UUID,
        product_id: UUID,
        monitoring_import_id: UUID,
        upload_id: UUID,
        parse_run_id: UUID,
    ) -> tuple[JobRecord, bool]:
        from apps.api.app.domain.monitoring import PROCESS_MONITORING_IMPORT_JOB_TYPE

        idempotency_key = f"process_monitoring_import:{monitoring_import_id}"
        for job in self._jobs.get(workspace_id, {}).values():
            if job.job_type == PROCESS_MONITORING_IMPORT_JOB_TYPE and job.idempotency_key == idempotency_key:
                return job, False
        now = datetime.now(UTC)
        job = JobRecord(
            id=uuid4(),
            workspace_id=workspace_id,
            job_type=PROCESS_MONITORING_IMPORT_JOB_TYPE,
            status=JobStatus.QUEUED,
            payload_json={
                "workspace_id": str(workspace_id),
                "product_id": str(product_id),
                "monitoring_import_id": str(monitoring_import_id),
                "upload_id": str(upload_id),
                "parse_run_id": str(parse_run_id),
            },
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        self._jobs.setdefault(workspace_id, {})[job.id] = job
        return job, True

    def get(self, *, workspace_id: UUID, job_id: UUID) -> JobRecord | None:
        return self._jobs.get(workspace_id, {}).get(job_id)

    def get_process_upload_job(self, *, workspace_id: UUID, upload_id: UUID) -> JobRecord | None:
        idempotency_key = _process_upload_idempotency_key(upload_id)
        for job in self._jobs.get(workspace_id, {}).values():
            if job.job_type == PROCESS_UPLOAD_JOB_TYPE and job.idempotency_key == idempotency_key:
                return job
        return None

    def claim_next(self, *, job_type: str, worker_id: str) -> JobRecord | None:
        queued_jobs = [
            job
            for jobs in self._jobs.values()
            for job in jobs.values()
            if job.job_type == job_type and job.status == JobStatus.QUEUED
        ]
        if not queued_jobs:
            return None
        current = sorted(queued_jobs, key=lambda job: job.created_at)[0]
        updated = current.model_copy(update={"status": JobStatus.RUNNING, "updated_at": datetime.now(UTC)})
        self._jobs[current.workspace_id][current.id] = updated
        return updated

    def update_status(self, *, workspace_id: UUID, job_id: UUID, status: JobStatus, last_error: str | None = None) -> JobRecord | None:
        current = self.get(workspace_id=workspace_id, job_id=job_id)
        if current is None:
            return None
        updated = current.model_copy(update={"status": status, "updated_at": datetime.now(UTC)})
        self._jobs[workspace_id][job_id] = updated
        return updated

    def delete_upload_jobs(self, *, workspace_id: UUID, upload_id: UUID) -> int:
        jobs = self._jobs.get(workspace_id, {})
        job_ids = [job_id for job_id, job in jobs.items() if job.payload_json.get("upload_id") == str(upload_id)]
        for job_id in job_ids:
            jobs.pop(job_id, None)
        return len(job_ids)

    def clear_queued_jobs(self, *, job_type: str | None = None) -> int:
        removed = 0
        for _, jobs in list(self._jobs.items()):
            for job_id, job in list(jobs.items()):
                if job.status != JobStatus.QUEUED:
                    continue
                if job_type is not None and job.job_type != job_type:
                    continue
                jobs.pop(job_id, None)
                removed += 1
        return removed


class PostgresJobRepository(JobRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def enqueue_process_upload(self, *, upload: UploadRecord) -> tuple[JobRecord, bool]:
        idempotency_key = _process_upload_idempotency_key(upload.id)
        now = _now_iso()
        job_id = uuid4()
        with self._engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    insert or ignore into job_queue (id, workspace_id, job_type, status, payload_json, idempotency_key, created_at, updated_at)
                    values (:id, :workspace_id, :job_type, 'queued', :payload_json, :idempotency_key, :created_at, :updated_at)
                    """
                ),
                {
                    "id": job_id,
                    "workspace_id": upload.workspace_id,
                    "job_type": PROCESS_UPLOAD_JOB_TYPE,
                    "payload_json": _json_dumps(_process_upload_payload(upload)),
                    "idempotency_key": idempotency_key,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            existing = connection.execute(
                text(
                    """
                    select id, workspace_id, job_type, status, payload_json, idempotency_key, created_at, updated_at
                    from job_queue
                    where workspace_id = :workspace_id
                        and job_type = :job_type
                        and idempotency_key = :idempotency_key
                    """
                ),
                {
                    "workspace_id": upload.workspace_id,
                    "job_type": PROCESS_UPLOAD_JOB_TYPE,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().one()
        return _job_from_row(existing), bool(result.rowcount)

    def enqueue_process_monitoring_import(
        self,
        *,
        workspace_id: UUID,
        product_id: UUID,
        monitoring_import_id: UUID,
        upload_id: UUID,
        parse_run_id: UUID,
    ) -> tuple[JobRecord, bool]:
        from apps.api.app.domain.monitoring import PROCESS_MONITORING_IMPORT_JOB_TYPE

        payload = {
            "workspace_id": str(workspace_id),
            "product_id": str(product_id),
            "monitoring_import_id": str(monitoring_import_id),
            "upload_id": str(upload_id),
            "parse_run_id": str(parse_run_id),
        }
        idempotency_key = f"process_monitoring_import:{monitoring_import_id}"
        now = _now_iso()
        job_id = uuid4()
        with self._engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    insert or ignore into job_queue (id, workspace_id, job_type, status, payload_json, idempotency_key, created_at, updated_at)
                    values (:id, :workspace_id, :job_type, 'queued', :payload_json, :idempotency_key, :created_at, :updated_at)
                    """
                ),
                {
                    "id": job_id,
                    "workspace_id": workspace_id,
                    "job_type": PROCESS_MONITORING_IMPORT_JOB_TYPE,
                    "payload_json": _json_dumps(payload),
                    "idempotency_key": idempotency_key,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            existing = connection.execute(
                text(
                    """
                    select id, workspace_id, job_type, status, payload_json, idempotency_key, created_at, updated_at
                    from job_queue
                    where workspace_id = :workspace_id and job_type = :job_type and idempotency_key = :idempotency_key
                    """
                ),
                {"workspace_id": workspace_id, "job_type": PROCESS_MONITORING_IMPORT_JOB_TYPE, "idempotency_key": idempotency_key},
            ).mappings().one()
        return _job_from_row(existing), bool(result.rowcount)

    def get(self, *, workspace_id: UUID, job_id: UUID) -> JobRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    select id, workspace_id, job_type, status, payload_json, idempotency_key, created_at, updated_at
                    from job_queue
                    where workspace_id = :workspace_id and id = :job_id
                    """
                ),
                {"workspace_id": workspace_id, "job_id": job_id},
            ).mappings().first()
        return _job_from_row(row) if row else None

    def get_process_upload_job(self, *, workspace_id: UUID, upload_id: UUID) -> JobRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    select id, workspace_id, job_type, status, payload_json, idempotency_key, created_at, updated_at
                    from job_queue
                    where workspace_id = :workspace_id
                        and job_type = :job_type
                        and idempotency_key = :idempotency_key
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "job_type": PROCESS_UPLOAD_JOB_TYPE,
                    "idempotency_key": _process_upload_idempotency_key(upload_id),
                },
            ).mappings().first()
        return _job_from_row(row) if row else None

    def claim_next(self, *, job_type: str, worker_id: str) -> JobRecord | None:
        now = _now_iso()
        stale_before = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        with self._engine.begin() as connection:
            # SQLite doesn't support FOR UPDATE SKIP LOCKED, so we use a simple
            # SELECT + UPDATE pattern with commit-level serialization.
            job_row = connection.execute(
                text(
                    """
                    select id, workspace_id, job_type, status, payload_json, idempotency_key, created_at, updated_at
                    from job_queue
                    where job_type = :job_type
                      and (
                        status = 'queued'
                        or (status = 'running' and locked_at is not null and locked_at < :stale_before)
                      )
                    order by case status when 'running' then 0 else 1 end, created_at asc
                    limit 1
                    """
                ),
                {"job_type": job_type, "stale_before": stale_before},
            ).mappings().first()
            if job_row is None:
                return None
            row = connection.execute(
                text(
                    """
                    update job_queue
                    set status = 'running',
                        locked_at = :now,
                        locked_by = :worker_id,
                        updated_at = :now
                    where id = :job_id
                      and (
                        status = 'queued'
                        or (status = 'running' and locked_at is not null and locked_at < :stale_before)
                      )
                    returning id, workspace_id, job_type, status, payload_json, idempotency_key, created_at, updated_at
                    """
                ),
                {"job_id": job_row["id"], "worker_id": worker_id, "now": now, "stale_before": stale_before},
            ).mappings().first()
        return _job_from_row(row) if row else None

    def update_status(self, *, workspace_id: UUID, job_id: UUID, status: JobStatus, last_error: str | None = None) -> JobRecord | None:
        now = _now_iso()
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update job_queue
                    set status = :status,
                        last_error = :last_error,
                        updated_at = :now
                    where workspace_id = :workspace_id and id = :job_id
                    returning id, workspace_id, job_type, status, payload_json, idempotency_key, created_at, updated_at
                    """
                ),
                {"workspace_id": workspace_id, "job_id": job_id, "status": status.value, "last_error": last_error, "now": now},
            ).mappings().first()
        return _job_from_row(row) if row else None

    def delete_upload_jobs(self, *, workspace_id: UUID, upload_id: UUID) -> int:
        with self._engine.begin() as connection:
            deleted = connection.execute(
                text(
                    """
                    delete from job_queue
                    where workspace_id = :workspace_id
                      and payload_json like :upload_pattern
                    """
                ),
                {"workspace_id": workspace_id, "upload_pattern": f'%"upload_id":"{upload_id}"%'},
            )
        return int(deleted.rowcount or 0)

    def clear_queued_jobs(self, *, job_type: str | None = None) -> int:
        params: dict[str, object] = {}
        clause = ["status = 'queued'"]
        if job_type is not None:
            clause.append("job_type = :job_type")
            params["job_type"] = job_type
        with self._engine.begin() as connection:
            deleted = connection.execute(text(f"delete from job_queue where {' and '.join(clause)}"), params)
        return int(deleted.rowcount or 0)


_local_repository = LocalJobRepository()


def get_job_repository() -> JobRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresJobRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def _process_upload_idempotency_key(upload_id: UUID) -> str:
    return f"process_upload:{upload_id}"


def _process_upload_payload(upload: UploadRecord) -> dict:
    return {
        "workspace_id": str(upload.workspace_id),
        "product_id": str(upload.product_id) if upload.product_id else None,
        "upload_id": str(upload.id),
        "storage_path": upload.storage_path,
        "source_type": upload.source_type.value,
    }


def _job_from_row(row: RowMapping) -> JobRecord:
    return JobRecord(
        id=row["id"],
        workspace_id=row["workspace_id"],
        job_type=row["job_type"],
        status=row["status"],
        payload_json=_json_loads(row["payload_json"]),
        idempotency_key=row["idempotency_key"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _json_dumps(value: dict) -> str:
    import json

    return json.dumps(value)


def _json_loads(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    import json

    return json.loads(value)
