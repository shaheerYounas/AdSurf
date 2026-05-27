from dataclasses import dataclass
from uuid import UUID

from apps.api.app.core.config import get_settings
from apps.api.app.core.errors import ApiError
from apps.api.app.domain.monitoring import PROCESS_MONITORING_IMPORT_JOB_TYPE
from apps.api.app.repositories.agent_control import AgentControlRepository, get_agent_control_repository, new_agent_event
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.jobs import JobRepository, get_job_repository
from apps.api.app.repositories.monitoring import MonitoringRepository, get_monitoring_repository
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository, get_upload_parsing_repository
from apps.api.app.schemas.jobs import JobRecord, JobStatus
from apps.api.app.schemas.monitoring import MonitoringImport, MonitoringImportStatus
from apps.api.app.services import monitoring_metrics
from apps.api.app.services.ai_recommendation_brain import (
    AI_RECOMMENDATION_MODES,
    DEEPSEEK_DECISION_SOURCE,
    FALLBACK_DECISION_SOURCE,
    AiRecommendationBrain,
    build_deterministic_recommendations,
)
from apps.api.app.services.monitoring_agents import build_failed_import_agent_run, build_monitoring_agent_runs
from apps.api.app.services.monitoring_rules import normalize_sp_search_term_rows
from apps.api.app.services.agent_registry import agent_id_for_run_name


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
        agent_control_repository: AgentControlRepository | None = None,
        worker_id: str = "monitoring-worker-local",
    ) -> None:
        self._job_repository = job_repository or get_job_repository()
        self._monitoring_repository = monitoring_repository or get_monitoring_repository()
        self._parsing_repository = parsing_repository or get_upload_parsing_repository()
        self._product_repository = product_repository or get_product_profile_repository()
        self._audit_repository = audit_repository or get_audit_log_repository()
        self._agent_control_repository = agent_control_repository or get_agent_control_repository()
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
            self._monitoring_repository.insert_snapshots(snapshots=snapshots)
            rollups = monitoring_metrics.build_performance_rollups(snapshots)
            recommendations, ai_runs, source, ai_error_warnings = self._build_recommendations_with_ai_mode(
                product=product,
                import_record=import_record,
                snapshots=snapshots,
                rollups=rollups,
                warnings=warnings,
            )
            warnings = [*warnings, *ai_error_warnings]
            if not recommendations and source == DEEPSEEK_DECISION_SOURCE:
                import_record = self._monitoring_repository.update_import(
                    workspace_id=import_record.workspace_id,
                    monitoring_import_id=import_record.id,
                    status=MonitoringImportStatus.FAILED,
                    total_rows=total,
                    processed_rows=len(snapshots),
                    error_rows=len(warnings),
                    data_quality_warnings_json=warnings,
                    error_message="AI recommendation generation failed validation or provider checks.",
                )
                self._job_repository.update_status(workspace_id=job.workspace_id, job_id=job.id, status=JobStatus.FAILED, last_error="AI recommendation generation failed validation or provider checks.")
                for ai_run in ai_runs:
                    ai_run = self._decorate_ai_run(ai_run=ai_run, import_record=import_record, recommendation_ids=[])
                    self._monitoring_repository.insert_ai_run(ai_run=ai_run)
                    self._record_agent_event(
                        workspace_id=import_record.workspace_id,
                        monitoring_import_id=import_record.id,
                        agent_run_id=ai_run.id,
                        agent_id=agent_id_for_run_name(ai_run.agent_name),
                        event_type="agent_failed",
                        message="AI recommendation generation failed validation or provider checks.",
                        metadata_json={"provider": ai_run.provider, "model": ai_run.model, "execution_boundary": "no_live_amazon_change"},
                    )
                self._audit_repository.record(
                    workspace_id=job.workspace_id,
                    actor_user_id="system",
                    action="monitoring_import.ai_recommendations_failed",
                    entity_type="monitoring_import",
                    entity_id=monitoring_import_id,
                    details={
                        "recommendation_source": source,
                        "ai_provider": ai_runs[0].provider if ai_runs else None,
                        "ai_model": ai_runs[0].model if ai_runs else None,
                        "number_of_recommendations": 0,
                        "execution_boundary": "no_live_amazon_change",
                        "validation_errors": ai_error_warnings,
                    },
                )
                return MonitoringWorkerResult(job=job, import_record=import_record, processed=True)
            self._monitoring_repository.insert_recommendations(recommendations=recommendations)
            for ai_run in ai_runs:
                ai_run = self._decorate_ai_run(ai_run=ai_run, import_record=import_record, recommendation_ids=[str(item.id) for item in recommendations])
                self._monitoring_repository.insert_ai_run(ai_run=ai_run)
                self._record_agent_event(
                    workspace_id=import_record.workspace_id,
                    monitoring_import_id=import_record.id,
                    agent_run_id=ai_run.id,
                    agent_id=agent_id_for_run_name(ai_run.agent_name),
                    event_type="agent_succeeded" if ai_run.status == "succeeded" else "agent_failed" if ai_run.status == "failed" else "agent_skipped",
                    message=f"{agent_id_for_run_name(ai_run.agent_name)} finished with status {ai_run.status}.",
                    metadata_json={"provider": ai_run.provider, "model": ai_run.model, "recommendation_count": len(recommendations), "execution_boundary": "no_live_amazon_change"},
                )
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
                details={
                    "snapshot_count": len(snapshots),
                    "recommendation_count": len(recommendations),
                    "recommendation_source": source,
                    "ai_provider": ai_runs[0].provider if ai_runs else None,
                    "ai_model": ai_runs[0].model if ai_runs else None,
                    "number_of_recommendations": len(recommendations),
                    "execution_boundary": "no_live_amazon_change",
                    "agent_run_ids": [str(run.id) for run in ai_runs],
                },
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
                    failed_run = self._decorate_ai_run(ai_run=failed_run, import_record=import_record, recommendation_ids=[])
                    self._monitoring_repository.insert_ai_run(ai_run=failed_run)
                    self._record_agent_event(
                        workspace_id=import_record.workspace_id,
                        monitoring_import_id=import_record.id,
                        agent_run_id=failed_run.id,
                        agent_id=agent_id_for_run_name(failed_run.agent_name),
                        event_type="agent_failed",
                        message=exc.message,
                        metadata_json={"error_code": exc.code, "execution_boundary": "no_live_amazon_change"},
                    )
                self._monitoring_repository.update_import(
                    workspace_id=import_record.workspace_id,
                    monitoring_import_id=import_record.id,
                    status=MonitoringImportStatus.FAILED,
                    error_message=message,
                    data_quality_warnings_json=warnings,
                )
            self._job_repository.update_status(workspace_id=job.workspace_id, job_id=job.id, status=JobStatus.FAILED, last_error=message)
            return MonitoringWorkerResult(job=job, import_record=import_record, processed=True)

    def _build_recommendations_with_ai_mode(self, *, product, import_record: MonitoringImport, snapshots, rollups: dict, warnings: list[dict]):
        settings = get_settings()
        mode = settings.ai_recommendation_mode if settings.ai_recommendation_mode in AI_RECOMMENDATION_MODES else "deterministic_fallback"
        brain_config = self._agent_control_repository.get_config(workspace_id=import_record.workspace_id, product_id=import_record.product_id, agent_id="ai_recommendation_brain_agent")
        if not brain_config.enabled or self._is_stopped(workspace_id=import_record.workspace_id, monitoring_import_id=import_record.id, agent_id="ai_recommendation_brain_agent"):
            fallback = build_deterministic_recommendations(
                product=product,
                import_record=import_record,
                snapshots=snapshots,
                decision_source=FALLBACK_DECISION_SOURCE,
            )
            local_runs = self._enabled_local_agent_runs(import_record=import_record, recommendations=fallback, snapshots=snapshots, warnings=warnings)
            self._record_agent_event(
                workspace_id=import_record.workspace_id,
                monitoring_import_id=import_record.id,
                agent_run_id=None,
                agent_id="ai_recommendation_brain_agent",
                event_type="agent_skipped",
                message="AI Recommendation Brain was disabled or stopped before execution.",
                metadata_json={"enabled": brain_config.enabled, "execution_boundary": "no_live_amazon_change"},
            )
            return fallback, local_runs, FALLBACK_DECISION_SOURCE, [{"code": "AGENT_SKIPPED", "message": "AI Recommendation Brain was disabled or stopped before execution.", "details": {"agent_id": "ai_recommendation_brain_agent"}}]
        baseline = None
        if mode == "hybrid":
            baseline = build_deterministic_recommendations(product=product, import_record=import_record, snapshots=snapshots)

        self._record_agent_event(
            workspace_id=import_record.workspace_id,
            monitoring_import_id=import_record.id,
            agent_run_id=None,
            agent_id="ai_recommendation_brain_agent",
            event_type="agent_started",
            message="AI Recommendation Brain started.",
            metadata_json={"mode": mode, "strictness_level": brain_config.strictness_level.value, "confidence_threshold": brain_config.confidence_threshold.value, "execution_boundary": "no_live_amazon_change"},
        )
        brain = AiRecommendationBrain()
        result = brain.generate(
            product=product,
            import_record=import_record,
            snapshots=snapshots,
            rollups=rollups,
            data_quality_warnings=warnings,
            baseline_recommendations=baseline,
            agent_config=brain_config,
        )
        ai_runs = [result.ai_run]
        if result.used_ai:
            return result.recommendations, ai_runs, DEEPSEEK_DECISION_SOURCE, []

        ai_warnings = [
            {
                "code": "AI_RECOMMENDATION_FAILED",
                "message": "AI recommendation generation failed validation or provider checks.",
                "details": {"validation_errors": result.validation_errors, "mode": mode},
            }
        ]
        if mode == "deepseek":
            return [], ai_runs, DEEPSEEK_DECISION_SOURCE, ai_warnings

        fallback = baseline or build_deterministic_recommendations(
            product=product,
            import_record=import_record,
            snapshots=snapshots,
            decision_source=FALLBACK_DECISION_SOURCE,
            ai_run=result.ai_run,
        )
        if mode == "hybrid":
            fallback = build_deterministic_recommendations(
                product=product,
                import_record=import_record,
                snapshots=snapshots,
                decision_source=FALLBACK_DECISION_SOURCE,
                ai_run=result.ai_run,
            )
        local_runs = self._enabled_local_agent_runs(
            import_record=import_record,
            recommendations=fallback,
            snapshots=snapshots,
            warnings=[*warnings, *ai_warnings],
        )
        return fallback, [*ai_runs, *local_runs], FALLBACK_DECISION_SOURCE, ai_warnings

    def _enabled_local_agent_runs(self, *, import_record: MonitoringImport, recommendations, snapshots, warnings: list[dict]):
        local_runs = build_monitoring_agent_runs(
            workspace_id=import_record.workspace_id,
            product_id=import_record.product_id,
            import_record=import_record,
            recommendations=recommendations,
            snapshots=snapshots,
            warnings=warnings,
        )
        enabled_runs = []
        for run in local_runs:
            agent_id = agent_id_for_run_name(run.agent_name)
            config = self._agent_control_repository.get_config(workspace_id=import_record.workspace_id, product_id=import_record.product_id, agent_id=agent_id)
            if config.enabled and not self._is_stopped(workspace_id=import_record.workspace_id, monitoring_import_id=import_record.id, agent_id=agent_id):
                enabled_runs.append(run)
                continue
            self._record_agent_event(
                workspace_id=import_record.workspace_id,
                monitoring_import_id=import_record.id,
                agent_run_id=run.id,
                agent_id=agent_id,
                event_type="agent_skipped",
                message=f"{agent_id} was disabled or stopped before execution.",
                metadata_json={"enabled": config.enabled, "execution_boundary": "no_live_amazon_change"},
            )
        return enabled_runs

    def _decorate_ai_run(self, *, ai_run, import_record: MonitoringImport, recommendation_ids: list[str]):
        agent_id = agent_id_for_run_name(ai_run.agent_name)
        config = self._agent_control_repository.get_config(workspace_id=import_record.workspace_id, product_id=import_record.product_id, agent_id=agent_id)
        metadata = {
            "agent_id": agent_id,
            "monitoring_import_id": str(import_record.id),
            "input_json": ai_run.output_json.get("input_json", {}),
            "recommendation_ids": recommendation_ids if agent_id == "ai_recommendation_brain_agent" else _related_recommendation_ids(agent_id=agent_id, recommendation_ids=recommendation_ids),
            "mode": config.mode.value,
            "strictness_level": config.strictness_level.value,
            "confidence_threshold": config.confidence_threshold.value,
            "can_mutate_live_amazon_ads": False,
            "requires_human_approval": True,
            "execution_boundary": "no_live_amazon_change",
        }
        return ai_run.model_copy(update={"output_json": {**ai_run.output_json, "_agent_control": metadata}})

    def _is_stopped(self, *, workspace_id: UUID, monitoring_import_id: UUID, agent_id: str) -> bool:
        action = self._agent_control_repository.latest_control_action(workspace_id=workspace_id, agent_id=agent_id, monitoring_import_id=monitoring_import_id)
        return bool(action and action.get("action") == "stop")

    def _record_agent_event(self, *, workspace_id: UUID, monitoring_import_id: UUID, agent_run_id: UUID | None, agent_id: str, event_type: str, message: str, metadata_json: dict) -> None:
        self._agent_control_repository.insert_event(
            event=new_agent_event(
                workspace_id=workspace_id,
                agent_id=agent_id,
                agent_run_id=agent_run_id,
                monitoring_import_id=monitoring_import_id,
                event_type=event_type,
                message=message,
                metadata_json=metadata_json,
            )
        )

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


def _related_recommendation_ids(*, agent_id: str, recommendation_ids: list[str]) -> list[str]:
    return recommendation_ids if agent_id in {"bid_optimization_agent", "negative_keyword_agent", "pause_review_agent", "stakeholder_reporting_agent"} else []
