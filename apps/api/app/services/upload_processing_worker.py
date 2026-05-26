from dataclasses import dataclass
from uuid import UUID, uuid4

from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import PROCESS_UPLOAD_JOB_TYPE
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.jobs import JobRepository, get_job_repository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository, get_upload_parsing_repository
from apps.api.app.repositories.uploads import UploadRepository, get_upload_repository
from apps.api.app.schemas.jobs import JobRecord, JobStatus
from apps.api.app.schemas.upload_parsing import UploadParseError, UploadParseRun, UploadParseStatus
from apps.api.app.schemas.uploads import UploadStatus
from apps.api.app.services.storage import StorageService, get_storage_service
from apps.api.app.services.upload_parser import UploadParser


@dataclass
class WorkerResult:
    job: JobRecord | None
    parse_run: UploadParseRun | None
    processed: bool


class UploadProcessingWorker:
    def __init__(
        self,
        *,
        job_repository: JobRepository | None = None,
        upload_repository: UploadRepository | None = None,
        parsing_repository: UploadParsingRepository | None = None,
        audit_repository: AuditLogRepository | None = None,
        storage_service: StorageService | None = None,
        parser: UploadParser | None = None,
        worker_id: str | None = None,
    ) -> None:
        self._job_repository = job_repository or get_job_repository()
        self._upload_repository = upload_repository or get_upload_repository()
        self._parsing_repository = parsing_repository or get_upload_parsing_repository()
        self._audit_repository = audit_repository or get_audit_log_repository()
        self._storage_service = storage_service or get_storage_service()
        self._parser = parser or UploadParser()
        self._worker_id = worker_id or f"upload-worker-{uuid4()}"

    def process_one(self) -> WorkerResult:
        job = self._job_repository.claim_next(job_type=PROCESS_UPLOAD_JOB_TYPE, worker_id=self._worker_id)
        if job is None:
            return WorkerResult(job=None, parse_run=None, processed=False)
        parse_run: UploadParseRun | None = None
        upload_id = job.payload_json.get("upload_id")
        try:
            if not upload_id:
                raise ApiError(code="PROCESS_UPLOAD_PAYLOAD_INVALID", message="Job payload is missing upload_id.", status_code=400)
            upload_uuid = UUID(str(upload_id))
            upload = self._upload_repository.get(workspace_id=job.workspace_id, upload_id=upload_uuid)
            if upload is None:
                raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)
            if upload.status != UploadStatus.QUEUED_FOR_PROCESSING:
                raise ApiError(code="UPLOAD_NOT_PROCESSABLE", message="Upload is not queued for processing.", status_code=409)

            self._upload_repository.update_status(workspace_id=upload.workspace_id, upload_id=upload.id, status=UploadStatus.PROCESSING)
            self._audit_repository.record(
                workspace_id=upload.workspace_id,
                actor_user_id="system",
                action="upload.processing_started",
                entity_type="upload",
                entity_id=upload.id,
                details={"job_id": str(job.id)},
            )

            parse_run = self._parsing_repository.create_run(
                upload=upload,
                job_id=job.id,
                detected_file_type=_file_type(upload.original_filename),
            )
            content = self._storage_service.read_upload_object(storage_path=upload.storage_path)
            result = self._parser.parse(content=content, original_filename=upload.original_filename, mime_type=upload.mime_type)
            self._parsing_repository.insert_rows(parse_run=parse_run, rows=result.rows)
            self._parsing_repository.insert_errors(parse_run=parse_run, errors=result.errors)
            parse_run = self._parsing_repository.complete_run(
                parse_run_id=parse_run.id,
                status=UploadParseStatus.SUCCEEDED,
                detected_file_type=result.detected_file_type,
                detected_sheet_names=result.detected_sheet_names,
                selected_sheet_name=result.selected_sheet_name,
                total_rows=result.total_rows,
                total_columns=result.total_columns,
                parsed_rows_count=len(result.rows),
                error_rows_count=len(result.errors),
            )
            self._upload_repository.update_status(workspace_id=upload.workspace_id, upload_id=upload.id, status=UploadStatus.PROCESSED)
            self._job_repository.update_status(workspace_id=job.workspace_id, job_id=job.id, status=JobStatus.SUCCEEDED)
            self._audit_repository.record(
                workspace_id=upload.workspace_id,
                actor_user_id="system",
                action="upload.parsed",
                entity_type="upload",
                entity_id=upload.id,
                details={"job_id": str(job.id), "parse_run_id": str(parse_run.id), "parsed_rows_count": len(result.rows)},
            )
            return WorkerResult(job=job, parse_run=parse_run, processed=True)
        except Exception as exc:
            message = _safe_error_message(exc)
            if parse_run is None and job.payload_json.get("upload_id"):
                upload = self._upload_repository.get(workspace_id=job.workspace_id, upload_id=UUID(str(job.payload_json["upload_id"])))
                if upload is not None:
                    parse_run = self._parsing_repository.create_run(
                        upload=upload,
                        job_id=job.id,
                        detected_file_type=_file_type(upload.original_filename),
                    )
            if parse_run is not None:
                self._parsing_repository.insert_errors(
                    parse_run=parse_run,
                    errors=[
                        UploadParseError(
                            row_number=None,
                            error_code=getattr(exc, "code", "UPLOAD_PARSE_FAILED"),
                            error_message=message,
                            raw_value_json=None,
                        )
                    ],
                )
                parse_run = self._parsing_repository.complete_run(
                    parse_run_id=parse_run.id,
                    status=UploadParseStatus.FAILED,
                    detected_file_type=parse_run.detected_file_type,
                    detected_sheet_names=parse_run.detected_sheet_names,
                    selected_sheet_name=parse_run.selected_sheet_name,
                    total_rows=0,
                    total_columns=0,
                    parsed_rows_count=0,
                    error_rows_count=1,
                    error_message=message,
                )
                self._upload_repository.update_status(workspace_id=parse_run.workspace_id, upload_id=parse_run.upload_id, status=UploadStatus.FAILED)
                self._audit_repository.record(
                    workspace_id=parse_run.workspace_id,
                    actor_user_id="system",
                    action="upload.parse_failed",
                    entity_type="upload",
                    entity_id=parse_run.upload_id,
                    details={"job_id": str(job.id), "parse_run_id": str(parse_run.id), "error_message": message},
                )
            self._job_repository.update_status(workspace_id=job.workspace_id, job_id=job.id, status=JobStatus.FAILED, last_error=message)
            return WorkerResult(job=job, parse_run=parse_run, processed=True)


def _file_type(filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
    return extension


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, ApiError):
        return exc.message
    return "Upload parsing failed."
