from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, status

from apps.api.app.core.auth import (
    PRODUCT_PROFILE_READ_ROLES,
    PRODUCT_PROFILE_WRITE_ROLES,
    WorkspacePrincipal,
    require_workspace_member,
)
from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import build_upload_storage_path, sanitize_upload_filename, validate_upload_request
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.column_mapping import ColumnMappingRepository, get_column_mapping_repository
from apps.api.app.repositories.jobs import JobRepository, get_job_repository
from apps.api.app.repositories.keyword_review import KeywordReviewRepository, get_keyword_review_repository
from apps.api.app.repositories.keyword_scoring import KeywordScoringRepository, get_keyword_scoring_repository
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository, get_upload_parsing_repository
from apps.api.app.repositories.uploads import UploadRepository, get_upload_repository
from apps.api.app.schemas.column_mapping import ColumnMappingCreateRequest, ColumnMappingStatus
from apps.api.app.schemas.envelope import success_response
from apps.api.app.schemas.keyword_review import (
    ApprovedKeywordSetCreateRequest,
    KeywordCandidateOverrideCreateRequest,
)
from apps.api.app.schemas.keyword_scoring import KeywordCandidateStatus, KeywordScoringSummary
from apps.api.app.schemas.uploads import (
    UploadConfirmRequest,
    UploadConfirmResponse,
    UploadInitRequest,
    UploadInitResponse,
    UploadStatus,
)
from apps.api.app.services.column_discovery import ColumnDiscoveryService
from apps.api.app.services.column_mapping import ColumnMappingService
from apps.api.app.services.keyword_scoring import KeywordScoringFailedError, KeywordScoringService
from apps.api.app.services.keyword_review import KeywordReviewService
from apps.api.app.services.storage import StorageService, get_storage_service

router = APIRouter()


@router.post(
    "/workspaces/{workspace_id}/products/{product_id}/uploads/init",
    status_code=status.HTTP_201_CREATED,
)
def initialize_upload(
    workspace_id: UUID,
    product_id: UUID,
    payload: UploadInitRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
    storage_service: StorageService = Depends(get_storage_service),
) -> dict:
    idempotency_key = _require_idempotency_key(idempotency_key)
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    product = product_repository.get(workspace_id=workspace_id, product_id=product_id)
    if product is None:
        raise ApiError(code="PRODUCT_NOT_FOUND", message="Product profile was not found.", status_code=404)

    sanitized_filename = sanitize_upload_filename(payload.original_filename)
    existing = upload_repository.get_by_idempotency_key(workspace_id=workspace_id, idempotency_key=idempotency_key)
    if existing is not None:
        _ensure_safe_init_replay(existing=existing, payload=payload, product_id=product_id, sanitized_filename=sanitized_filename)
        signed_target = storage_service.create_signed_upload_url(
            storage_path=existing.storage_path,
            mime_type=existing.mime_type,
        )
        response = UploadInitResponse(
            upload_id=existing.id,
            storage_path=existing.storage_path,
            upload_url=signed_target.upload_url,
            upload_url_expires_at=signed_target.expires_at,
            status=existing.status,
        )
        return success_response(data=response.model_dump(mode="json"))

    sanitized_filename = validate_upload_request(
        original_filename=payload.original_filename,
        mime_type=payload.mime_type,
        file_size_bytes=payload.file_size_bytes,
        source_type=payload.source_type,
    )
    upload_id = uuid4()
    storage_path = build_upload_storage_path(
        workspace_id=workspace_id,
        product_id=product_id,
        upload_id=upload_id,
        sanitized_filename=sanitized_filename,
    )
    upload = upload_repository.create_initialized(
        upload_id=upload_id,
        workspace_id=workspace_id,
        product_id=product_id,
        payload=payload,
        storage_path=storage_path,
        actor_user_id=principal.user_id,
        idempotency_key=idempotency_key,
    )
    signed_target = storage_service.create_signed_upload_url(storage_path=upload.storage_path, mime_type=upload.mime_type)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="upload.initialized",
        entity_type="upload",
        entity_id=upload.id,
        details={"product_id": str(product_id), "source_type": upload.source_type.value},
    )
    response = UploadInitResponse(
        upload_id=upload.id,
        storage_path=upload.storage_path,
        upload_url=signed_target.upload_url,
        upload_url_expires_at=signed_target.expires_at,
        status=upload.status,
    )
    return success_response(data=response.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/uploads/{upload_id}/confirm")
def confirm_upload(
    workspace_id: UUID,
    upload_id: UUID,
    payload: UploadConfirmRequest | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    job_repository: JobRepository = Depends(get_job_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    _require_idempotency_key(idempotency_key)
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    upload = upload_repository.get(workspace_id=workspace_id, upload_id=upload_id)
    if upload is None:
        raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)

    existing_job = job_repository.get_process_upload_job(workspace_id=workspace_id, upload_id=upload_id)
    if upload.status == UploadStatus.QUEUED_FOR_PROCESSING and existing_job is not None:
        response = UploadConfirmResponse(upload_id=upload.id, status=upload.status, job_id=existing_job.id)
        return success_response(data=response.model_dump(mode="json"))
    if upload.status != UploadStatus.INITIALIZED:
        raise ApiError(code="UPLOAD_NOT_CONFIRMABLE", message="Upload cannot be confirmed from its current status.", status_code=409)
    if existing_job is not None:
        raise ApiError(code="UPLOAD_JOB_CONFLICT", message="Upload already has a processing job.", status_code=409)

    updated_upload = upload_repository.mark_queued_for_processing(workspace_id=workspace_id, upload_id=upload_id)
    if updated_upload is None:
        raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)
    if updated_upload.status != UploadStatus.QUEUED_FOR_PROCESSING:
        raise ApiError(code="UPLOAD_NOT_CONFIRMABLE", message="Upload cannot be confirmed from its current status.", status_code=409)

    job, job_created = job_repository.enqueue_process_upload(upload=updated_upload)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="upload.confirmed",
        entity_type="upload",
        entity_id=upload_id,
        details={"checksum_reserved": bool(payload and payload.checksum)},
    )
    if job_created:
        audit_repository.record(
            workspace_id=workspace_id,
            actor_user_id=principal.user_id,
            action="job.queued",
            entity_type="job",
            entity_id=job.id,
            details={"job_type": job.job_type, "upload_id": str(upload_id)},
        )
    response = UploadConfirmResponse(upload_id=updated_upload.id, status=updated_upload.status, job_id=job.id)
    return success_response(data=response.model_dump(mode="json"))


@router.put("/workspaces/{workspace_id}/uploads/{upload_id}/object")
async def upload_object_bytes(
    workspace_id: UUID,
    upload_id: UUID,
    request: Request,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    storage_service: StorageService = Depends(get_storage_service),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    upload = upload_repository.get(workspace_id=workspace_id, upload_id=upload_id)
    if upload is None:
        raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)
    if upload.status != UploadStatus.INITIALIZED:
        raise ApiError(code="UPLOAD_NOT_WRITABLE", message="Upload object can only be written before confirmation.", status_code=409)
    content = await request.body()
    if len(content) != upload.file_size_bytes:
        raise ApiError(
            code="UPLOAD_SIZE_MISMATCH",
            message="Uploaded object size does not match initialization metadata.",
            status_code=400,
            details={"expected_bytes": upload.file_size_bytes, "actual_bytes": len(content)},
        )
    storage_service.write_upload_object(storage_path=upload.storage_path, content=content)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="upload.object_stored",
        entity_type="upload",
        entity_id=upload_id,
        details={"file_size_bytes": len(content)},
    )
    return success_response(data=upload.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/uploads")
def list_uploads(
    workspace_id: UUID,
    product_id: UUID | None = Query(default=None),
    upload_status: UploadStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    uploads, total = upload_repository.list(
        workspace_id=workspace_id,
        product_id=product_id,
        status=upload_status,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data=[upload.model_dump(mode="json") for upload in uploads],
        meta={"total": total, "page": page, "page_size": page_size, "has_next": page * page_size < total},
    )


@router.get("/workspaces/{workspace_id}/uploads/{upload_id}")
def get_upload(
    workspace_id: UUID,
    upload_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    upload = upload_repository.get(workspace_id=workspace_id, upload_id=upload_id)
    if upload is None:
        raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)
    return success_response(data=upload.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs")
def list_upload_parse_runs(
    workspace_id: UUID,
    upload_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _require_upload(workspace_id=workspace_id, upload_id=upload_id, upload_repository=upload_repository)
    runs = parsing_repository.list_runs(workspace_id=workspace_id, upload_id=upload_id)
    return success_response(data=[run.model_dump(mode="json") for run in runs], meta={"total": len(runs)})


@router.get("/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}")
def get_upload_parse_run(
    workspace_id: UUID,
    upload_id: UUID,
    parse_run_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _require_upload(workspace_id=workspace_id, upload_id=upload_id, upload_repository=upload_repository)
    parse_run = parsing_repository.get_run(workspace_id=workspace_id, upload_id=upload_id, parse_run_id=parse_run_id)
    if parse_run is None:
        raise ApiError(code="PARSE_RUN_NOT_FOUND", message="Parse run was not found.", status_code=404)
    return success_response(data=parse_run.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}/rows")
def list_upload_parse_rows(
    workspace_id: UUID,
    upload_id: UUID,
    parse_run_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _require_parse_run(
        workspace_id=workspace_id,
        upload_id=upload_id,
        parse_run_id=parse_run_id,
        upload_repository=upload_repository,
        parsing_repository=parsing_repository,
    )
    rows, total = parsing_repository.list_rows(workspace_id=workspace_id, parse_run_id=parse_run_id, page=page, page_size=page_size)
    return success_response(
        data=[row.model_dump(mode="json") for row in rows],
        meta={"total": total, "page": page, "page_size": page_size, "has_next": page * page_size < total},
    )


@router.get("/workspaces/{workspace_id}/uploads/{upload_id}/parse-runs/{parse_run_id}/errors")
def list_upload_parse_errors(
    workspace_id: UUID,
    upload_id: UUID,
    parse_run_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _require_parse_run(
        workspace_id=workspace_id,
        upload_id=upload_id,
        parse_run_id=parse_run_id,
        upload_repository=upload_repository,
        parsing_repository=parsing_repository,
    )
    errors, total = parsing_repository.list_errors(workspace_id=workspace_id, parse_run_id=parse_run_id, page=page, page_size=page_size)
    return success_response(
        data=[error.model_dump(mode="json") for error in errors],
        meta={"total": total, "page": page, "page_size": page_size, "has_next": page * page_size < total},
    )


@router.post("/workspaces/{workspace_id}/uploads/{upload_id}/column-profile")
def generate_column_profile(
    workspace_id: UUID,
    upload_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
    column_repository: ColumnMappingRepository = Depends(get_column_mapping_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    _require_upload(workspace_id=workspace_id, upload_id=upload_id, upload_repository=upload_repository)
    result = ColumnDiscoveryService(parsing_repository=parsing_repository, column_repository=column_repository).generate_for_upload(
        workspace_id=workspace_id,
        upload_id=upload_id,
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="column_profile.generated",
        entity_type="upload_column_profile",
        entity_id=result.profile.id,
        details={"upload_id": str(upload_id), "parse_run_id": str(result.profile.parse_run_id), "total_columns": result.profile.total_columns},
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/uploads/{upload_id}/column-profile")
def get_column_profile(
    workspace_id: UUID,
    upload_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
    column_repository: ColumnMappingRepository = Depends(get_column_mapping_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _require_upload(workspace_id=workspace_id, upload_id=upload_id, upload_repository=upload_repository)
    result = ColumnDiscoveryService(parsing_repository=parsing_repository, column_repository=column_repository).get_for_upload(
        workspace_id=workspace_id,
        upload_id=upload_id,
    )
    if result is None:
        raise ApiError(code="COLUMN_PROFILE_NOT_FOUND", message="Column profile was not found.", status_code=404)
    return success_response(data=result.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings")
def create_column_mapping(
    workspace_id: UUID,
    upload_id: UUID,
    payload: ColumnMappingCreateRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    column_repository: ColumnMappingRepository = Depends(get_column_mapping_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    _require_upload(workspace_id=workspace_id, upload_id=upload_id, upload_repository=upload_repository)
    mapping = ColumnMappingService(column_repository=column_repository).create_manual_mapping(
        workspace_id=workspace_id,
        upload_id=upload_id,
        column_profile_id=payload.column_profile_id,
        mapping_json=payload.mapping_json,
        created_by=principal.user_id,
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="column_mapping.invalid" if mapping.status == ColumnMappingStatus.INVALID else "column_mapping.created",
        entity_type="upload_column_mapping",
        entity_id=mapping.id,
        details={"upload_id": str(upload_id), "column_profile_id": str(payload.column_profile_id), "status": mapping.status.value},
    )
    return success_response(data=mapping.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/uploads/{upload_id}/column-mappings")
def list_column_mappings(
    workspace_id: UUID,
    upload_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    column_repository: ColumnMappingRepository = Depends(get_column_mapping_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _require_upload(workspace_id=workspace_id, upload_id=upload_id, upload_repository=upload_repository)
    mappings, total = column_repository.list_mappings(workspace_id=workspace_id, upload_id=upload_id, page=page, page_size=page_size)
    return success_response(
        data=[mapping.model_dump(mode="json") for mapping in mappings],
        meta={"total": total, "page": page, "page_size": page_size, "has_next": page * page_size < total},
    )


@router.post("/workspaces/{workspace_id}/column-mappings/{mapping_id}/approve")
def approve_column_mapping(
    workspace_id: UUID,
    mapping_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    column_repository: ColumnMappingRepository = Depends(get_column_mapping_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    mapping = column_repository.approve_mapping(workspace_id=workspace_id, mapping_id=mapping_id)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="column_mapping.approved",
        entity_type="upload_column_mapping",
        entity_id=mapping.id,
        details={"upload_id": str(mapping.upload_id), "column_profile_id": str(mapping.column_profile_id)},
    )
    return success_response(data=mapping.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/column-mappings/{mapping_id}/score")
def score_column_mapping(
    workspace_id: UUID,
    mapping_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    column_repository: ColumnMappingRepository = Depends(get_column_mapping_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
    scoring_repository: KeywordScoringRepository = Depends(get_keyword_scoring_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    idempotency_key = _require_idempotency_key(idempotency_key)
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    try:
        result = KeywordScoringService(
            column_repository=column_repository,
            parsing_repository=parsing_repository,
            scoring_repository=scoring_repository,
        ).score_mapping(workspace_id=workspace_id, mapping_id=mapping_id, idempotency_key=idempotency_key)
    except KeywordScoringFailedError as exc:
        audit_repository.record(
            workspace_id=workspace_id,
            actor_user_id=principal.user_id,
            action="keyword_scoring.failed",
            entity_type="keyword_scoring_run",
            entity_id=exc.run.id,
            details={"column_mapping_id": str(mapping_id), "error_message": exc.message},
        )
        raise ApiError(code="KEYWORD_SCORING_FAILED", message="Keyword scoring failed.", status_code=500) from exc
    if result.created:
        audit_repository.record(
            workspace_id=workspace_id,
            actor_user_id=principal.user_id,
            action="keyword_scoring.started",
            entity_type="keyword_scoring_run",
            entity_id=result.run.id,
            details={"column_mapping_id": str(mapping_id), "idempotency_key": idempotency_key},
        )
        audit_repository.record(
            workspace_id=workspace_id,
            actor_user_id=principal.user_id,
            action="keyword_scoring.completed",
            entity_type="keyword_scoring_run",
            entity_id=result.run.id,
            details={
                "column_mapping_id": str(mapping_id),
                "approved_count": result.run.approved_count,
                "rejected_count": result.run.rejected_count,
                "error_count": result.run.error_count,
            },
        )
    return success_response(data=_scoring_summary(result.run).model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}")
def get_scoring_run(
    workspace_id: UUID,
    scoring_run_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    scoring_repository: KeywordScoringRepository = Depends(get_keyword_scoring_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    run = scoring_repository.get_run(workspace_id=workspace_id, scoring_run_id=scoring_run_id)
    if run is None:
        raise ApiError(code="KEYWORD_SCORING_RUN_NOT_FOUND", message="Keyword scoring run was not found.", status_code=404)
    return success_response(data=run.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates")
def list_scoring_candidates(
    workspace_id: UUID,
    scoring_run_id: UUID,
    scoring_status: KeywordCandidateStatus | None = Query(default=None),
    min_relevance_score: int | None = Query(default=None, ge=0, le=10),
    max_relevance_score: int | None = Query(default=None, ge=0, le=10),
    search_term: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    scoring_repository: KeywordScoringRepository = Depends(get_keyword_scoring_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    run = scoring_repository.get_run(workspace_id=workspace_id, scoring_run_id=scoring_run_id)
    if run is None:
        raise ApiError(code="KEYWORD_SCORING_RUN_NOT_FOUND", message="Keyword scoring run was not found.", status_code=404)
    candidates, total = scoring_repository.list_candidates(
        workspace_id=workspace_id,
        scoring_run_id=scoring_run_id,
        scoring_status=scoring_status,
        min_relevance_score=min_relevance_score,
        max_relevance_score=max_relevance_score,
        search_term=search_term,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data=[candidate.model_dump(mode="json") for candidate in candidates],
        meta={"total": total, "page": page, "page_size": page_size, "has_next": page * page_size < total},
    )


@router.post("/workspaces/{workspace_id}/keyword-candidates/{candidate_id}/override")
def create_keyword_candidate_override(
    workspace_id: UUID,
    candidate_id: UUID,
    payload: KeywordCandidateOverrideCreateRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    scoring_repository: KeywordScoringRepository = Depends(get_keyword_scoring_repository),
    review_repository: KeywordReviewRepository = Depends(get_keyword_review_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    override = KeywordReviewService(scoring_repository=scoring_repository, review_repository=review_repository).create_override(
        workspace_id=workspace_id,
        keyword_candidate_id=candidate_id,
        override_action=payload.override_action,
        reason=payload.reason,
        created_by=principal.user_id,
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="keyword_candidate.override_created",
        entity_type="keyword_candidate_override",
        entity_id=override.id,
        details={
            "keyword_candidate_id": str(candidate_id),
            "scoring_run_id": str(override.scoring_run_id),
            "new_status": override.new_status.value,
        },
    )
    return success_response(data=override.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/candidates/review")
def list_scoring_candidate_reviews(
    workspace_id: UUID,
    scoring_run_id: UUID,
    effective_status: KeywordCandidateStatus | None = Query(default=None),
    original_status: KeywordCandidateStatus | None = Query(default=None),
    has_override: bool | None = Query(default=None),
    min_relevance_score: int | None = Query(default=None, ge=0, le=10),
    max_relevance_score: int | None = Query(default=None, ge=0, le=10),
    search_term: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    scoring_repository: KeywordScoringRepository = Depends(get_keyword_scoring_repository),
    review_repository: KeywordReviewRepository = Depends(get_keyword_review_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    reviews, total = KeywordReviewService(scoring_repository=scoring_repository, review_repository=review_repository).list_reviews(
        workspace_id=workspace_id,
        scoring_run_id=scoring_run_id,
        effective_status=effective_status,
        original_status=original_status,
        has_override=has_override,
        min_relevance_score=min_relevance_score,
        max_relevance_score=max_relevance_score,
        search_term=search_term,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data=[review.model_dump(mode="json") for review in reviews],
        meta={"total": total, "page": page, "page_size": page_size, "has_next": page * page_size < total},
    )


@router.post("/workspaces/{workspace_id}/scoring-runs/{scoring_run_id}/approved-keyword-sets")
def create_approved_keyword_set(
    workspace_id: UUID,
    scoring_run_id: UUID,
    payload: ApprovedKeywordSetCreateRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    scoring_repository: KeywordScoringRepository = Depends(get_keyword_scoring_repository),
    review_repository: KeywordReviewRepository = Depends(get_keyword_review_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    keyword_set = KeywordReviewService(scoring_repository=scoring_repository, review_repository=review_repository).create_approved_keyword_set(
        workspace_id=workspace_id,
        scoring_run_id=scoring_run_id,
        name=payload.name,
        created_by=principal.user_id,
    )
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="approved_keyword_set.created",
        entity_type="approved_keyword_set",
        entity_id=keyword_set.id,
        details={"scoring_run_id": str(scoring_run_id), "keyword_count": keyword_set.keyword_count},
    )
    return success_response(data=keyword_set.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/approved-keyword-sets/{keyword_set_id}")
def get_approved_keyword_set(
    workspace_id: UUID,
    keyword_set_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    scoring_repository: KeywordScoringRepository = Depends(get_keyword_scoring_repository),
    review_repository: KeywordReviewRepository = Depends(get_keyword_review_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    keyword_set = KeywordReviewService(scoring_repository=scoring_repository, review_repository=review_repository).get_keyword_set(
        workspace_id=workspace_id,
        keyword_set_id=keyword_set_id,
    )
    return success_response(data=keyword_set.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/approved-keyword-sets/{keyword_set_id}/items")
def list_approved_keyword_set_items(
    workspace_id: UUID,
    keyword_set_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    scoring_repository: KeywordScoringRepository = Depends(get_keyword_scoring_repository),
    review_repository: KeywordReviewRepository = Depends(get_keyword_review_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    items, total = KeywordReviewService(scoring_repository=scoring_repository, review_repository=review_repository).list_keyword_set_items(
        workspace_id=workspace_id,
        keyword_set_id=keyword_set_id,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data=[item.model_dump(mode="json") for item in items],
        meta={"total": total, "page": page, "page_size": page_size, "has_next": page * page_size < total},
    )


@router.get("/workspaces/{workspace_id}/jobs/{job_id}")
def get_job(
    workspace_id: UUID,
    job_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    job_repository: JobRepository = Depends(get_job_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    job = job_repository.get(workspace_id=workspace_id, job_id=job_id)
    if job is None:
        raise ApiError(code="JOB_NOT_FOUND", message="Job was not found.", status_code=404)
    return success_response(data=job.model_dump(mode="json"))


def _scoring_summary(run) -> KeywordScoringSummary:
    return KeywordScoringSummary(
        scoring_run_id=run.id,
        status=run.status,
        total_rows=run.total_rows,
        scored_rows=run.scored_rows,
        approved_count=run.approved_count,
        rejected_count=run.rejected_count,
        error_count=run.error_count,
    )


def _require_idempotency_key(value: str | None) -> str:
    normalized = value.strip() if value else ""
    if not normalized:
        raise ApiError(
            code="IDEMPOTENCY_KEY_REQUIRED",
            message="Idempotency-Key header is required.",
            status_code=400,
        )
    return normalized


def _require_upload(*, workspace_id: UUID, upload_id: UUID, upload_repository: UploadRepository):
    upload = upload_repository.get(workspace_id=workspace_id, upload_id=upload_id)
    if upload is None:
        raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)
    return upload


def _require_parse_run(
    *,
    workspace_id: UUID,
    upload_id: UUID,
    parse_run_id: UUID,
    upload_repository: UploadRepository,
    parsing_repository: UploadParsingRepository,
):
    _require_upload(workspace_id=workspace_id, upload_id=upload_id, upload_repository=upload_repository)
    parse_run = parsing_repository.get_run(workspace_id=workspace_id, upload_id=upload_id, parse_run_id=parse_run_id)
    if parse_run is None:
        raise ApiError(code="PARSE_RUN_NOT_FOUND", message="Parse run was not found.", status_code=404)
    return parse_run


def _ensure_safe_init_replay(
    *,
    existing,
    payload: UploadInitRequest,
    product_id: UUID,
    sanitized_filename: str,
) -> None:
    expected = {
        "product_id": str(product_id),
        "original_filename": payload.original_filename,
        "sanitized_filename": sanitized_filename,
        "mime_type": payload.mime_type,
        "file_size_bytes": payload.file_size_bytes,
        "source_type": payload.source_type,
    }
    actual = {
        "product_id": str(existing.product_id),
        "original_filename": existing.original_filename,
        "sanitized_filename": existing.storage_path.rsplit("/", 1)[-1],
        "mime_type": existing.mime_type,
        "file_size_bytes": existing.file_size_bytes,
        "source_type": existing.source_type.value,
    }
    if existing.status != UploadStatus.INITIALIZED:
        raise ApiError(
            code="IDEMPOTENCY_KEY_CONFLICT",
            message="Idempotency-Key cannot be replayed after upload initialization has advanced.",
            status_code=409,
        )
    if actual != expected:
        raise ApiError(
            code="IDEMPOTENCY_KEY_CONFLICT",
            message="Idempotency-Key was already used for a different upload initialization request.",
            status_code=409,
            details={"fields": sorted(field for field in expected if expected[field] != actual[field])},
        )
