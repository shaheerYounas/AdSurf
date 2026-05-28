from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends

from apps.api.app.core.auth import PRODUCT_PROFILE_READ_ROLES, PRODUCT_PROFILE_WRITE_ROLES, WorkspacePrincipal, require_workspace_member
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.account_imports import AccountImportRepository, get_account_import_repository
from apps.api.app.repositories.agent_control import AgentControlRepository, get_agent_control_repository
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.monitoring import MonitoringRepository, get_monitoring_repository
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository, get_upload_parsing_repository
from apps.api.app.repositories.uploads import UploadRepository, get_upload_repository
from apps.api.app.repositories.workflows import WorkflowRepository, get_workflow_repository
from apps.api.app.schemas.account_imports import AccountImportCreateRequest, AccountImportResponse
from apps.api.app.schemas.envelope import success_response
from apps.api.app.services.account_import_builder import create_account_import_from_processed_upload, latest_succeeded_parse_run, load_rows
from apps.api.app.services.report_type_detector import ReportTypeDetector
from apps.api.app.services.workflow_queue import enqueue_account_import_workflow

router = APIRouter()


@router.post("/workspaces/{workspace_id}/account-imports")
def create_account_import(
    workspace_id: UUID,
    payload: AccountImportCreateRequest,
    background_tasks: BackgroundTasks,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
    account_import_repository: AccountImportRepository = Depends(get_account_import_repository),
    workflow_repository: WorkflowRepository = Depends(get_workflow_repository),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    agent_control_repository: AgentControlRepository = Depends(get_agent_control_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    result = create_account_import_from_processed_upload(
        workspace_id=workspace_id,
        upload_id=payload.upload_id,
        actor_user_id=principal.user_id,
        upload_repository=upload_repository,
        parsing_repository=parsing_repository,
        product_repository=product_repository,
        account_import_repository=account_import_repository,
        workflow_repository=workflow_repository,
    )
    enqueue_account_import_workflow(
        background_tasks=background_tasks,
        workflow_repository=workflow_repository,
        account_import_repository=account_import_repository,
        monitoring_repository=monitoring_repository,
        workflow_id=result.workflow.id,
        workspace_id=workspace_id,
        account_import_id=result.import_record.id,
        upload_id=result.import_record.upload_id,
        agent_config={config.agent_id: config.model_dump(mode="json") for config in agent_control_repository.list_configs(workspace_id=workspace_id)},
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="account_import.created",
        entity_type="account_import",
        entity_id=result.import_record.id,
        details={
            "upload_id": str(result.import_record.upload_id),
            "parse_run_id": str(result.import_record.parse_run_id),
            "detected_report_type": result.detection.detected_report_type.value,
            "detection_confidence": result.detection.confidence.value,
            "entity_count": len(result.resolution.entities),
            "mapping_suggestion_count": len(result.resolution.product_mapping_suggestions),
            "workflow_id": str(result.workflow.id),
            "execution_boundary": "analysis_only_no_live_amazon_change",
        },
    )
    return success_response(
        data=AccountImportResponse(
            import_record=result.import_record,
            detection=result.detection,
            entities=result.resolution.entities,
            product_mapping_suggestions=result.resolution.product_mapping_suggestions,
            workflow_id=result.workflow.id,
        ).model_dump(mode="json")
    )

@router.get("/workspaces/{workspace_id}/uploads/{upload_id}/report-detection")
def detect_upload_report_type(
    workspace_id: UUID,
    upload_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    upload = upload_repository.get(workspace_id=workspace_id, upload_id=upload_id)
    if upload is None:
        raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)
    parse_run = latest_succeeded_parse_run(workspace_id=workspace_id, upload_id=upload.id, parsing_repository=parsing_repository)
    rows = load_rows(workspace_id=workspace_id, parse_run_id=parse_run.id, parsing_repository=parsing_repository, limit=25)
    detection = ReportTypeDetector().detect(headers=rows[0].row_data_json.keys() if rows else [], sample_rows=[row.row_data_json for row in rows])
    return success_response(data=detection.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/account-imports")
def list_account_imports(
    workspace_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    account_import_repository: AccountImportRepository = Depends(get_account_import_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    imports = account_import_repository.list_imports(workspace_id=workspace_id)
    return success_response(data=[item.model_dump(mode="json") for item in imports], meta={"total": len(imports)})


@router.get("/workspaces/{workspace_id}/account-imports/{account_import_id}")
def get_account_import(
    workspace_id: UUID,
    account_import_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    account_import_repository: AccountImportRepository = Depends(get_account_import_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    import_record = account_import_repository.get_import(workspace_id=workspace_id, account_import_id=account_import_id)
    if import_record is None:
        raise ApiError(code="ACCOUNT_IMPORT_NOT_FOUND", message="Account import was not found.", status_code=404)
    entities = account_import_repository.list_entities(workspace_id=workspace_id, account_import_id=account_import_id)
    suggestions = account_import_repository.list_mapping_suggestions(workspace_id=workspace_id, account_import_id=account_import_id)
    return success_response(
        data={
            "import_record": import_record.model_dump(mode="json"),
            "entities": [entity.model_dump(mode="json") for entity in entities],
            "product_mapping_suggestions": [suggestion.model_dump(mode="json") for suggestion in suggestions],
        }
    )


@router.get("/workspaces/{workspace_id}/account-imports/{account_import_id}/entities")
def list_account_import_entities(
    workspace_id: UUID,
    account_import_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    account_import_repository: AccountImportRepository = Depends(get_account_import_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _require_import(workspace_id=workspace_id, account_import_id=account_import_id, repository=account_import_repository)
    entities = account_import_repository.list_entities(workspace_id=workspace_id, account_import_id=account_import_id)
    return success_response(data=[entity.model_dump(mode="json") for entity in entities], meta={"total": len(entities)})


@router.get("/workspaces/{workspace_id}/account-imports/{account_import_id}/product-mapping-suggestions")
def list_product_mapping_suggestions(
    workspace_id: UUID,
    account_import_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    account_import_repository: AccountImportRepository = Depends(get_account_import_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _require_import(workspace_id=workspace_id, account_import_id=account_import_id, repository=account_import_repository)
    suggestions = account_import_repository.list_mapping_suggestions(workspace_id=workspace_id, account_import_id=account_import_id)
    return success_response(data=[suggestion.model_dump(mode="json") for suggestion in suggestions], meta={"total": len(suggestions)})


def _require_import(*, workspace_id: UUID, account_import_id: UUID, repository: AccountImportRepository):
    import_record = repository.get_import(workspace_id=workspace_id, account_import_id=account_import_id)
    if import_record is None:
        raise ApiError(code="ACCOUNT_IMPORT_NOT_FOUND", message="Account import was not found.", status_code=404)
    return import_record
