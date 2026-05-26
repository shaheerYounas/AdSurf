from dataclasses import dataclass
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.domain.monitoring import PROCESS_MONITORING_IMPORT_JOB_TYPE
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.jobs import JobRepository, get_job_repository
from apps.api.app.repositories.monitoring import MonitoringRepository, get_monitoring_repository
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository, get_upload_parsing_repository
from apps.api.app.schemas.jobs import JobRecord, JobStatus
from apps.api.app.schemas.monitoring import MonitoringImport, MonitoringImportStatus
from apps.api.app.services.monitoring_agents import build_failed_import_agent_run, build_monitoring_agent_runs
from apps.api.app.services.monitoring_rules import build_recommendations, normalize_sp_search_term_rows


@dataclass
class MonitoringWorkerResult:
    job: JobRecord | None
    import_record: MonitoringImport | None
    processed: bool


class MonitoringWorker:
    def __init__(
        self,
        *,
        job_repository: JobRepository | None = None,
        monitoring_repository: MonitoringRepository | None = None,
        parsing_repository: UploadParsingRepository | None = None,
        product_repository: ProductProfileRepository | None = None,
        audit_repository: AuditLogRepository | None = None,
        worker_id: str = "monitoring-worker-local",
    ) -> None:
        self._job_repository = job_repository or get_job_repository()
        self._monitoring_repository = monitoring_repository or get_monitoring_repository()
        self._parsing_repository = parsing_repository or get_upload_parsing_repository()
        self._product_repository = product_repository or get_product_profile_repository()
        self._audit_repository = audit_repository or get_audit_log_repository()
        self._worker_id = worker_id

    def process_one(self) -> MonitoringWorkerResult:
        job = self._job_repository.claim_next(job_type=PROCESS_MONITORING_IMPORT_JOB_TYPE, worker_id=self._worker_id)
        if job is None:
            return MonitoringWorkerResult(job=None, import_record=None, processed=False)
        import_record: MonitoringImport | None = None
        try:
            monitoring_import_id = UUID(str(job.payload_json["monitoring_import_id"]))
            import_record = self._monitoring_repository.get_import(workspace_id=job.workspace_id, monitoring_import_id=monitoring_import_id)
            if import_record is None:
                raise ApiError(code="MONITORING_IMPORT_NOT_FOUND", message="Monitoring import was not found.", status_code=404)
            if import_record.status != MonitoringImportStatus.QUEUED:
                raise ApiError(code="MONITORING_IMPORT_NOT_PROCESSABLE", message="Monitoring import is not queued.", status_code=409)
            product = self._product_repository.get(workspace_id=import_record.workspace_id, product_id=import_record.product_id)
            if product is None:
                raise ApiError(code="PRODUCT_NOT_FOUND", message="Product profile was not found.", status_code=404)

            self._monitoring_repository.update_import(workspace_id=import_record.workspace_id, monitoring_import_id=import_record.id, status=MonitoringImportStatus.PROCESSING)
            rows, total = self._load_all_rows(import_record)
            snapshots, warnings = normalize_sp_search_term_rows(import_record=import_record, rows=rows)
            recommendations = build_recommendations(product=product, import_record=import_record, snapshots=snapshots)
            self._monitoring_repository.insert_snapshots(snapshots=snapshots)
            self._monitoring_repository.insert_recommendations(recommendations=recommendations)
            ai_runs = build_monitoring_agent_runs(
                workspace_id=import_record.workspace_id,
                product_id=import_record.product_id,
                import_record=import_record,
                recommendations=recommendations,
                snapshots=snapshots,
                warnings=warnings,
            )
            for ai_run in ai_runs:
                self._monitoring_repository.insert_ai_run(ai_run=ai_run)
            date_range_start = min((snapshot.start_date for snapshot in snapshots if snapshot.start_date), default=None)
            date_range_end = max((snapshot.end_date for snapshot in snapshots if snapshot.end_date), default=None)
            import_record = self._monitoring_repository.update_import(
                workspace_id=import_record.workspace_id,
                monitoring_import_id=import_record.id,
                status=MonitoringImportStatus.SUCCEEDED,
                total_rows=total,
                processed_rows=len(snapshots),
                error_rows=len(warnings),
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                data_quality_warnings_json=warnings,
            )
            self._job_repository.update_status(workspace_id=job.workspace_id, job_id=job.id, status=JobStatus.SUCCEEDED)
            self._audit_repository.record(
                workspace_id=job.workspace_id,
                actor_user_id="system",
                action="monitoring_import.processed",
                entity_type="monitoring_import",
                entity_id=monitoring_import_id,
                details={"snapshot_count": len(snapshots), "recommendation_count": len(recommendations), "agent_run_ids": [str(run.id) for run in ai_runs]},
            )
            return MonitoringWorkerResult(job=job, import_record=import_record, processed=True)
        except Exception as exc:
            message = exc.message if isinstance(exc, ApiError) else "Monitoring import failed."
            if import_record is not None:
                warnings = []
                if isinstance(exc, ApiError):
                    warnings = [{"code": exc.code, "message": exc.message, "details": exc.details}]
                    failed_run = build_failed_import_agent_run(
                        workspace_id=import_record.workspace_id,
                        product_id=import_record.product_id,
                        import_record=import_record,
                        error_code=exc.code,
                        message=exc.message,
                        details=exc.details,
                    )
                    self._monitoring_repository.insert_ai_run(ai_run=failed_run)
                self._monitoring_repository.update_import(
                    workspace_id=import_record.workspace_id,
                    monitoring_import_id=import_record.id,
                    status=MonitoringImportStatus.FAILED,
                    error_message=message,
                    data_quality_warnings_json=warnings,
                )
            self._job_repository.update_status(workspace_id=job.workspace_id, job_id=job.id, status=JobStatus.FAILED, last_error=message)
            return MonitoringWorkerResult(job=job, import_record=import_record, processed=True)

    def _load_all_rows(self, import_record: MonitoringImport):
        rows = []
        page = 1
        while True:
            page_rows, total = self._parsing_repository.list_rows(
                workspace_id=import_record.workspace_id,
                parse_run_id=import_record.parse_run_id,
                page=page,
                page_size=500,
            )
            rows.extend(page_rows)
            if len(rows) >= total:
                return rows, total
            page += 1
