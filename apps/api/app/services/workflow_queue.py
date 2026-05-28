import logging
from uuid import UUID

from fastapi import BackgroundTasks

from apps.api.app.core.config import get_settings
from apps.api.app.orchestration.ads_workflow_graph import AdsWorkflowRunner
from apps.api.app.repositories.account_imports import AccountImportRepository
from apps.api.app.repositories.monitoring import MonitoringRepository
from apps.api.app.repositories.workflows import WorkflowRepository
from apps.api.app.schemas.workflows import WorkflowStatus


def enqueue_account_import_workflow(
    *,
    background_tasks: BackgroundTasks | None,
    workflow_repository: WorkflowRepository,
    account_import_repository: AccountImportRepository,
    monitoring_repository: MonitoringRepository,
    workflow_id: UUID,
    workspace_id: UUID,
    account_import_id: UUID,
    upload_id: UUID | None,
    agent_config: dict | None = None,
) -> None:
    settings = get_settings()
    if settings.queue_backend == "celery":
        # Celery is intentionally not required for the MVP local path yet. Keep
        # the workflow durable and visible, then run through the local adapter.
        logging.info("QUEUE_BACKEND=celery requested, but Celery worker is not configured. Falling back to local workflow runner.")
    if background_tasks is not None:
        background_tasks.add_task(
            run_account_import_workflow_task,
            workflow_repository,
            account_import_repository,
            monitoring_repository,
            workflow_id,
            workspace_id,
            account_import_id,
            upload_id,
            agent_config or {},
        )
        return
    run_account_import_workflow_task(
        workflow_repository,
        account_import_repository,
        monitoring_repository,
        workflow_id,
        workspace_id,
        account_import_id,
        upload_id,
        agent_config or {},
    )


def run_account_import_workflow_task(
    workflow_repository: WorkflowRepository,
    account_import_repository: AccountImportRepository,
    monitoring_repository: MonitoringRepository,
    workflow_id: UUID,
    workspace_id: UUID,
    account_import_id: UUID,
    upload_id: UUID | None,
    agent_config: dict,
) -> None:
    try:
        AdsWorkflowRunner(
            workflow_repository=workflow_repository,
            account_import_repository=account_import_repository,
            monitoring_repository=monitoring_repository,
        ).run_account_import_workflow(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            account_import_id=account_import_id,
            upload_id=upload_id,
            agent_config=agent_config,
        )
    except Exception as exc:  # noqa: BLE001 - background failures must be persisted.
        logging.exception("Account import workflow failed")
        workflow_repository.update_workflow(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            status=WorkflowStatus.FAILED,
            current_node="failure",
            error_json={"message": str(exc), "executes_live_amazon_change": False},
            completed=True,
        )
