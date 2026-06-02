from uuid import UUID, uuid4

from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Body, Depends, Query, Request, status

from apps.api.app.core.auth import (
    PRODUCT_PROFILE_READ_ROLES,
    PRODUCT_PROFILE_WRITE_ROLES,
    WorkspacePrincipal,
    require_workspace_member,
)
from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import build_upload_storage_path, sanitize_upload_filename
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.competitor_cleaned import CompetitorCleanedRepository, get_competitor_cleaned_repository
from apps.api.app.schemas.competitor_cleaned import CompetitorAgenticVerificationRequest, CompetitorAgenticVerificationResponse, CompetitorCleanedRowsResponse, CampaignGenerationResponse, CompetitorScoringResponse, CompetitorUpload, CompetitorUploadResponse, CompetitorVerificationRequest, CompetitorVerificationResponse
from apps.api.app.schemas.envelope import success_response
from apps.api.app.services.competitor_campaign_gen import CompetitorCampaignGenerationService
from apps.api.app.services.competitor_cleaner import CompetitorCleanerService
from apps.api.app.services.competitor_scoring import CompetitorScoringService
from apps.api.app.services.competitor_verification import CompetitorVerificationService
from apps.api.app.services.monitoring_14day import Monitoring14DayService
from apps.api.app.services.storage import StorageService, get_storage_service

router = APIRouter()


@router.post("/workspaces/{workspace_id}/competitor-uploads", status_code=status.HTTP_201_CREATED)
async def upload_competitor_csv(
    workspace_id: UUID,
    request: Request,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: CompetitorCleanedRepository = Depends(get_competitor_cleaned_repository),
    storage_service: StorageService = Depends(get_storage_service),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    try:
        form = await request.form()
    except Exception as exc:
        raise ApiError(
            code="MULTIPART_UPLOAD_REQUIRED",
            message="Competitor upload requires multipart/form-data with a file field.",
            status_code=400,
        ) from exc
    file_part = form.get("file")
    if file_part is None or not hasattr(file_part, "read"):
        raise ApiError(code="COMPETITOR_FILE_REQUIRED", message="Competitor upload requires a file field.", status_code=400)
    content = await file_part.read()
    filename = getattr(file_part, "filename", "") or "competitor.csv"
    mime_type = getattr(file_part, "content_type", None) or "text/csv"
    if not content:
        raise ApiError(code="COMPETITOR_FILE_EMPTY", message="Competitor file cannot be empty.", status_code=400)
    file_size = len(content)

    sanitized = sanitize_upload_filename(filename)
    upload_id = uuid4()
    storage_path = build_upload_storage_path(
        workspace_id=workspace_id,
        product_id=None,
        upload_id=upload_id,
        sanitized_filename=sanitized,
    )

    upload = repository.create_upload(
        upload_id=upload_id,
        workspace_id=workspace_id,
        product_id=None,
        original_filename=filename,
        storage_path=storage_path,
        mime_type=mime_type,
        file_size_bytes=file_size,
        uploaded_by=principal.user_id,
    )
    storage_service.write_upload_object(storage_path=upload.storage_path, content=content)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="competitor_upload.received",
        entity_type="competitor_upload",
        entity_id=upload.id,
        details={"file_size_bytes": file_size, "original_filename": filename},
    )

    cleaner = CompetitorCleanerService(repository=repository)
    result = cleaner.process(upload=upload, content=content)

    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="competitor_upload.cleaned",
        entity_type="competitor_upload",
        entity_id=result.upload.id,
        details={
            "row_count": result.upload.row_count,
            "cleaned_column_count": result.upload.cleaned_column_count,
            "warning_count": len(result.warnings),
        },
    )

    return success_response(data=CompetitorUploadResponse(
        upload=result.upload,
        cleaned_rows=result.rows[:20],
        total_rows=len(result.rows),
        warnings=result.warnings,
    ).model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/competitor-uploads/{upload_id}/score")
def score_competitor_upload(
    workspace_id: UUID,
    upload_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: CompetitorCleanedRepository = Depends(get_competitor_cleaned_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    scorer = CompetitorScoringService(repository=repository)
    result = scorer.score_upload(workspace_id=workspace_id, upload_id=upload_id)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="competitor_upload.scored",
        entity_type="competitor_upload",
        entity_id=upload_id,
        details={
            "total_rows": result.total_rows,
            "approved_count": result.approved_count,
            "rejected_count": result.rejected_count,
            "error_count": result.error_count,
        },
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/competitor-uploads/{upload_id}/verify")
def verify_competitor_keywords(
    workspace_id: UUID,
    upload_id: UUID,
    payload: CompetitorVerificationRequest = Body(...),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: CompetitorCleanedRepository = Depends(get_competitor_cleaned_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    verifier = CompetitorVerificationService(repository=repository)
    result = verifier.verify(
        workspace_id=workspace_id,
        upload_id=upload_id,
        competitors=payload.competitors,
        evidence_rows=payload.evidence_rows,
        evidence_text_rows=payload.evidence_text_rows,
        required_match_count=payload.required_match_count,
        verification_method=payload.verification_method,
    )
    audit_repository.record(
        workspace_id=workspace_id, actor_user_id=principal.user_id,
        action="competitor_upload.verified", entity_type="competitor_upload", entity_id=upload_id,
        details={
            "verified_count": result.verified_count,
            "unverified_count": result.unverified_count,
            "verification_method": payload.verification_method,
            "required_match_count": payload.required_match_count,
        },
    )
    upload = repository.get_upload(workspace_id=workspace_id, upload_id=upload_id)
    return success_response(data=CompetitorVerificationResponse(
        upload=upload,
        verified_count=result.verified_count,
        unverified_count=result.unverified_count,
        total_count=result.total_count,
        preview_rows=result.preview_rows,
    ).model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/competitor-uploads/{upload_id}/verify-agentic")
def verify_competitor_keywords_agentic(
    workspace_id: UUID,
    upload_id: UUID,
    payload: CompetitorAgenticVerificationRequest = Body(...),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: CompetitorCleanedRepository = Depends(get_competitor_cleaned_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    verifier = CompetitorVerificationService(repository=repository)
    result, evidence_rows = verifier.verify_with_browser_agent(
        workspace_id=workspace_id,
        upload_id=upload_id,
        competitors=payload.competitors,
        required_match_count=payload.required_match_count,
        max_keywords=payload.max_keywords,
        marketplace=payload.marketplace,
        headless=payload.headless,
        timeout_ms=payload.timeout_ms,
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="competitor_upload.agentic_verified",
        entity_type="competitor_upload",
        entity_id=upload_id,
        details={
            "verified_count": result.verified_count,
            "unverified_count": result.unverified_count,
            "verification_method": "agentic_browser_search",
            "required_match_count": payload.required_match_count,
            "max_keywords": payload.max_keywords,
            "marketplace": payload.marketplace,
            "evidence_row_count": len(evidence_rows),
            "executes_live_amazon_change": False,
        },
    )
    upload = repository.get_upload(workspace_id=workspace_id, upload_id=upload_id)
    return success_response(data=CompetitorAgenticVerificationResponse(
        upload=upload,
        verified_count=result.verified_count,
        unverified_count=result.unverified_count,
        total_count=result.total_count,
        preview_rows=result.preview_rows,
        evidence_rows=evidence_rows,
    ).model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/competitor-uploads/{upload_id}/generate-campaigns")
def generate_campaigns_from_verified(
    workspace_id: UUID,
    upload_id: UUID,
    product_id: UUID = Body(...),
    product_name: str = Body("Product"),
    batch_size: int = Body(7, ge=5, le=7),
    daily_budget: float = Body(10.0),
    default_bid: float = Body(1.0),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: CompetitorCleanedRepository = Depends(get_competitor_cleaned_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    gen = CompetitorCampaignGenerationService(repository=repository)
    result = gen.generate_from_verified(
        workspace_id=workspace_id, upload_id=upload_id, product_id=product_id,
        product_name=product_name, batch_size=batch_size,
        daily_budget=Decimal(str(daily_budget)), default_bid=Decimal(str(default_bid)),
    )
    audit_repository.record(
        workspace_id=workspace_id, actor_user_id=principal.user_id,
        action="competitor_upload.campaigns_generated", entity_type="competitor_upload", entity_id=upload_id,
        details={"campaign_count": result.campaign_count, "hero": result.hero_campaign_name},
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/monitoring/14day-simulation")
def simulate_14day_monitoring(
    workspace_id: UUID,
    product_id: UUID = Body(...),
    campaign_name: str = Body(...),
    daily_budget: float = Body(10.0),
    starting_bid: float = Body(1.0),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    monitor = Monitoring14DayService()
    results = monitor.simulate_14day_cycle(
        workspace_id=workspace_id, product_id=product_id, campaign_name=campaign_name,
        daily_budget=Decimal(str(daily_budget)), starting_bid=Decimal(str(starting_bid)),
    )
    audit_repository.record(
        workspace_id=workspace_id, actor_user_id=principal.user_id,
        action="monitoring.14day_simulation", entity_type="campaign", entity_id=product_id,
        details={"campaign_name": campaign_name, "days_simulated": len(results)},
    )
    return success_response(data=[{
        "day": r.day, "date": str(r.date_snapshot), "spend": str(r.spend),
        "daily_budget": str(r.daily_budget), "budget_consumed_pct": str(r.budget_consumed_pct),
        "impressions": r.impressions, "clicks": r.clicks, "orders": r.orders,
        "sales": str(r.sales), "acos": str(r.acos) if r.acos else None,
        "action": r.action, "previous_bid": str(r.previous_bid),
        "suggested_bid": str(r.suggested_bid), "locked": r.locked,
        "day7_checkpoint": r.day7_checkpoint,
    } for r in results])


@router.get("/workspaces/{workspace_id}/competitor-uploads")
def list_competitor_uploads(
    workspace_id: UUID,
    product_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: CompetitorCleanedRepository = Depends(get_competitor_cleaned_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    uploads, total = repository.list_uploads(
        workspace_id=workspace_id,
        product_id=product_id,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data=[upload.model_dump(mode="json") for upload in uploads],
        meta={"total": total, "page": page, "page_size": page_size, "has_next": page * page_size < total},
    )


@router.get("/workspaces/{workspace_id}/competitor-uploads/{upload_id}")
def get_competitor_upload(
    workspace_id: UUID,
    upload_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: CompetitorCleanedRepository = Depends(get_competitor_cleaned_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    upload = repository.get_upload(workspace_id=workspace_id, upload_id=upload_id)
    if upload is None:
        raise ApiError(code="COMPETITOR_UPLOAD_NOT_FOUND", message="Competitor upload was not found.", status_code=404)
    return success_response(data=upload.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/competitor-uploads/{upload_id}/rows")
def list_competitor_cleaned_rows(
    workspace_id: UUID,
    upload_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: CompetitorCleanedRepository = Depends(get_competitor_cleaned_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    upload = repository.get_upload(workspace_id=workspace_id, upload_id=upload_id)
    if upload is None:
        raise ApiError(code="COMPETITOR_UPLOAD_NOT_FOUND", message="Competitor upload was not found.", status_code=404)
    rows, total = repository.list_rows(
        workspace_id=workspace_id,
        competitor_upload_id=upload_id,
        page=page,
        page_size=page_size,
    )
    return success_response(data=CompetitorCleanedRowsResponse(
        rows=rows,
        upload=upload,
        total=total,
        page=page,
        page_size=page_size,
        has_next=page * page_size < total,
    ).model_dump(mode="json"))
