from uuid import UUID

from fastapi import APIRouter, Depends, Query

from apps.api.app.core.auth import PRODUCT_PROFILE_READ_ROLES, PRODUCT_PROFILE_WRITE_ROLES, WorkspacePrincipal, WorkspaceRole, require_workspace_member
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.jobs import JobRepository, get_job_repository
from apps.api.app.repositories.monitoring import MonitoringRepository, get_monitoring_repository, new_monitoring_import
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository, get_upload_parsing_repository
from apps.api.app.repositories.uploads import UploadRepository, get_upload_repository
from apps.api.app.schemas.envelope import success_response
from apps.api.app.schemas.monitoring import (
    MonitoringImportCreateRequest,
    MonitoringImportResponse,
    MonitoringSummary,
    RecommendationDecisionRequest,
    RecommendationStatus,
)
from apps.api.app.schemas.upload_parsing import UploadParseStatus
from apps.api.app.schemas.uploads import UploadSourceType, UploadStatus

router = APIRouter()

RECOMMENDATION_DECISION_ROLES = {
    WorkspaceRole.OWNER,
    WorkspaceRole.ADMIN,
    WorkspaceRole.ANALYST,
    WorkspaceRole.APPROVER,
}


@router.post("/workspaces/{workspace_id}/products/{product_id}/monitoring-imports")
@router.post("/workspaces/{workspace_id}/products/{product_id}/monitoring/imports")
def create_monitoring_import(
    workspace_id: UUID,
    product_id: UUID,
    payload: MonitoringImportCreateRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    job_repository: JobRepository = Depends(get_job_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    product = product_repository.get(workspace_id=workspace_id, product_id=product_id)
    if product is None:
        raise ApiError(code="PRODUCT_NOT_FOUND", message="Product profile was not found.", status_code=404)
    upload = upload_repository.get(workspace_id=workspace_id, upload_id=payload.upload_id)
    if upload is None or upload.product_id != product_id:
        raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)
    if upload.source_type != UploadSourceType.AMAZON_ADS_SP_SEARCH_TERM_REPORT:
        raise ApiError(
            code="MONITORING_UPLOAD_SOURCE_TYPE_INVALID",
            message="Monitoring import requires an Amazon Sponsored Products Search Term report upload.",
            status_code=409,
        )
    if upload.status != UploadStatus.PROCESSED:
        raise ApiError(code="UPLOAD_NOT_PROCESSED", message="Monitoring import requires a processed upload.", status_code=409)
    parse_runs = parsing_repository.list_runs(workspace_id=workspace_id, upload_id=upload.id)
    parse_run = next((run for run in parse_runs if run.status == UploadParseStatus.SUCCEEDED), None)
    if parse_run is None:
        raise ApiError(code="PARSE_RUN_NOT_FOUND", message="Monitoring import requires a succeeded parse run.", status_code=409)

    import_record = monitoring_repository.create_import(
        import_record=new_monitoring_import(
            workspace_id=workspace_id,
            product_id=product_id,
            upload_id=upload.id,
            parse_run_id=parse_run.id,
            created_by=principal.user_id,
        )
    )
    job, created = job_repository.enqueue_process_monitoring_import(
        workspace_id=workspace_id,
        product_id=product_id,
        monitoring_import_id=import_record.id,
        upload_id=upload.id,
        parse_run_id=parse_run.id,
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="monitoring_import.queued",
        entity_type="monitoring_import",
        entity_id=import_record.id,
        details={"upload_id": str(upload.id), "parse_run_id": str(parse_run.id), "job_created": created},
    )
    response = MonitoringImportResponse(import_record=import_record, job_id=job.id)
    return success_response(data=response.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/monitoring/imports/{import_id}/run-analysis")
def run_monitoring_analysis(
    workspace_id: UUID,
    import_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    job_repository: JobRepository = Depends(get_job_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    import_record = monitoring_repository.get_import(workspace_id=workspace_id, monitoring_import_id=import_id)
    if import_record is None:
        raise ApiError(code="MONITORING_IMPORT_NOT_FOUND", message="Monitoring import was not found.", status_code=404)
    if import_record.status not in {"queued", "failed"}:
        return success_response(data={"import_record": import_record.model_dump(mode="json"), "job_created": False})
    job, created = job_repository.enqueue_process_monitoring_import(
        workspace_id=workspace_id,
        product_id=import_record.product_id,
        monitoring_import_id=import_record.id,
        upload_id=import_record.upload_id,
        parse_run_id=import_record.parse_run_id,
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="monitoring_import.analysis_queued",
        entity_type="monitoring_import",
        entity_id=import_record.id,
        details={"job_id": str(job.id), "job_created": created},
    )
    return success_response(data={"import_record": import_record.model_dump(mode="json"), "job_id": str(job.id), "job_created": created})


@router.get("/workspaces/{workspace_id}/products/{product_id}/monitoring")
@router.get("/workspaces/{workspace_id}/products/{product_id}/monitoring/summary")
def get_product_monitoring(
    workspace_id: UUID,
    product_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    product = product_repository.get(workspace_id=workspace_id, product_id=product_id)
    if product is None:
        raise ApiError(code="PRODUCT_NOT_FOUND", message="Product profile was not found.", status_code=404)
    imports = monitoring_repository.list_imports(workspace_id=workspace_id, product_id=product_id)
    recommendations = monitoring_repository.list_recommendations(workspace_id=workspace_id, product_id=product_id)
    product_summaries = monitoring_repository.list_ai_runs(workspace_id=workspace_id, product_id=product_id, agent_name="stakeholder_reporting_agent")
    latest_summary = product_summaries[0] if product_summaries else monitoring_repository.latest_ai_run(workspace_id=workspace_id, agent_name="stakeholder_reporting_agent")
    counts: dict[str, int] = {}
    for recommendation in recommendations:
        counts[recommendation.status.value] = counts.get(recommendation.status.value, 0) + 1
        counts[recommendation.recommendation_type.value] = counts.get(recommendation.recommendation_type.value, 0) + 1
    summary = MonitoringSummary(
        imports=imports[:10],
        recommendation_counts=counts,
        top_recommendations=recommendations[:10],
        agent_summary=latest_summary.output_json if latest_summary else None,
    )
    return success_response(data=summary.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/products/{product_id}/agent-runs")
def list_product_agent_runs(
    workspace_id: UUID,
    product_id: UUID,
    agent_name: str | None = Query(default=None),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    product = product_repository.get(workspace_id=workspace_id, product_id=product_id)
    if product is None:
        raise ApiError(code="PRODUCT_NOT_FOUND", message="Product profile was not found.", status_code=404)
    runs = monitoring_repository.list_ai_runs(workspace_id=workspace_id, product_id=product_id, agent_name=agent_name)
    return success_response(data=[run.model_dump(mode="json") for run in runs], meta={"total": len(runs)})


@router.get("/workspaces/{workspace_id}/recommendations")
@router.get("/workspaces/{workspace_id}/products/{product_id}/recommendations")
def list_recommendations(
    workspace_id: UUID,
    product_id: UUID | None = None,
    status: RecommendationStatus | None = Query(default=None),
    recommendation_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=250, ge=1, le=1000),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    recommendations = monitoring_repository.list_recommendations(
        workspace_id=workspace_id,
        product_id=product_id,
        status=status,
        recommendation_type=recommendation_type,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return success_response(data=[recommendation.model_dump(mode="json") for recommendation in recommendations], meta={"page": page, "page_size": page_size, "returned": len(recommendations)})


@router.get("/workspaces/{workspace_id}/recommendations/{recommendation_id}")
def get_recommendation(
    workspace_id: UUID,
    recommendation_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    recommendation = monitoring_repository.get_recommendation(workspace_id=workspace_id, recommendation_id=recommendation_id)
    if recommendation is None:
        raise ApiError(code="RECOMMENDATION_NOT_FOUND", message="Recommendation was not found.", status_code=404)
    return success_response(data=recommendation.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/recommendations/{recommendation_id}/approve")
def approve_recommendation(
    workspace_id: UUID,
    recommendation_id: UUID,
    payload: RecommendationDecisionRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    return _decide_recommendation(
        workspace_id=workspace_id,
        recommendation_id=recommendation_id,
        decision=RecommendationStatus.APPROVED,
        payload=payload,
        principal=principal,
        monitoring_repository=monitoring_repository,
        audit_repository=audit_repository,
    )


@router.post("/workspaces/{workspace_id}/recommendations/{recommendation_id}/reject")
def reject_recommendation(
    workspace_id: UUID,
    recommendation_id: UUID,
    payload: RecommendationDecisionRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    return _decide_recommendation(
        workspace_id=workspace_id,
        recommendation_id=recommendation_id,
        decision=RecommendationStatus.REJECTED,
        payload=payload,
        principal=principal,
        monitoring_repository=monitoring_repository,
        audit_repository=audit_repository,
    )


def _decide_recommendation(
    *,
    workspace_id: UUID,
    recommendation_id: UUID,
    decision: RecommendationStatus,
    payload: RecommendationDecisionRequest,
    principal: WorkspacePrincipal,
    monitoring_repository: MonitoringRepository,
    audit_repository: AuditLogRepository,
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(RECOMMENDATION_DECISION_ROLES)
    recommendation, decision_record = monitoring_repository.decide_recommendation(
        workspace_id=workspace_id,
        recommendation_id=recommendation_id,
        decision=decision,
        actor_user_id=principal.user_id,
        note=payload.note,
    )
    if recommendation is None or decision_record is None:
        raise ApiError(code="RECOMMENDATION_NOT_DECIDABLE", message="Recommendation was not found or is already decided.", status_code=409)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action=f"recommendation.{decision.value}",
        entity_type="recommendation",
        entity_id=recommendation_id,
        details={"decision_id": str(decision_record.id), "note": payload.note.strip(), "execution_boundary": "no_live_amazon_change"},
    )
    return success_response(data=recommendation.model_dump(mode="json"))
