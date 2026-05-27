from uuid import UUID

from fastapi import APIRouter, Depends

from apps.api.app.core.auth import PRODUCT_PROFILE_READ_ROLES, PRODUCT_PROFILE_WRITE_ROLES, WorkspacePrincipal, require_workspace_member
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.account_imports import AccountImportRepository, get_account_import_repository, new_account_import
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository, get_upload_parsing_repository
from apps.api.app.repositories.uploads import UploadRepository, get_upload_repository
from apps.api.app.schemas.account_imports import AccountImportCreateRequest, AccountImportResponse, AccountImportStatus
from apps.api.app.schemas.envelope import success_response
from apps.api.app.schemas.upload_parsing import ParsedUploadRow, UploadParseStatus
from apps.api.app.schemas.uploads import UploadStatus
from apps.api.app.services.product_entity_resolver import ProductEntityResolver
from apps.api.app.services.report_type_detector import ReportTypeDetector

router = APIRouter()


@router.post("/workspaces/{workspace_id}/account-imports")
def create_account_import(
    workspace_id: UUID,
    payload: AccountImportCreateRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    parsing_repository: UploadParsingRepository = Depends(get_upload_parsing_repository),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
    account_import_repository: AccountImportRepository = Depends(get_account_import_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    upload = upload_repository.get(workspace_id=workspace_id, upload_id=payload.upload_id)
    if upload is None:
        raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)
    if upload.status != UploadStatus.PROCESSED:
        raise ApiError(code="UPLOAD_NOT_PROCESSED", message="Account import requires a processed upload.", status_code=409)
    parse_run = _latest_succeeded_parse_run(workspace_id=workspace_id, upload_id=upload.id, parsing_repository=parsing_repository)
    rows = _load_rows(workspace_id=workspace_id, parse_run_id=parse_run.id, parsing_repository=parsing_repository)
    if not rows:
        raise ApiError(code="ACCOUNT_IMPORT_EMPTY", message="Account import requires parsed rows.", status_code=409)

    detection = ReportTypeDetector().detect(headers=rows[0].row_data_json.keys(), sample_rows=[row.row_data_json for row in rows[:25]])
    warnings = []
    if not detection.required_columns_present:
        warnings.append(
            {
                "code": "REPORT_COLUMNS_MISSING",
                "message": "Detected report is missing columns required for full analysis.",
                "details": {"missing_columns": detection.missing_columns, "detected_report_type": detection.detected_report_type.value},
            }
        )
    import_record = new_account_import(
        workspace_id=workspace_id,
        upload_id=upload.id,
        parse_run_id=parse_run.id,
        report_type=upload.source_type,
        detected_report_type=detection.detected_report_type,
        detection_confidence=detection.confidence,
        total_rows=len(rows),
        processed_rows=0,
        error_rows=len(warnings),
        warnings=warnings,
        created_by=principal.user_id,
        needs_mapping=False,
    )
    resolution = ProductEntityResolver().resolve(
        import_record=import_record,
        rows=rows,
        existing_products=product_repository.list(workspace_id),
    )
    status = AccountImportStatus.READY_FOR_ANALYSIS
    if not detection.required_columns_present:
        status = AccountImportStatus.DETECTED
    elif resolution.product_mapping_suggestions:
        status = AccountImportStatus.NEEDS_MAPPING
    import_record = import_record.model_copy(update={"status": status, "processed_rows": len(rows)})
    import_record = account_import_repository.create_import(import_record=import_record)
    account_import_repository.insert_entities(entities=resolution.entities)
    account_import_repository.insert_mapping_suggestions(suggestions=resolution.product_mapping_suggestions)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="account_import.created",
        entity_type="account_import",
        entity_id=import_record.id,
        details={
            "upload_id": str(upload.id),
            "parse_run_id": str(parse_run.id),
            "detected_report_type": detection.detected_report_type.value,
            "detection_confidence": detection.confidence.value,
            "entity_count": len(resolution.entities),
            "mapping_suggestion_count": len(resolution.product_mapping_suggestions),
            "execution_boundary": "analysis_only_no_live_amazon_change",
        },
    )
    return success_response(
        data=AccountImportResponse(
            import_record=import_record,
            detection=detection,
            entities=resolution.entities,
            product_mapping_suggestions=resolution.product_mapping_suggestions,
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
    parse_run = _latest_succeeded_parse_run(workspace_id=workspace_id, upload_id=upload.id, parsing_repository=parsing_repository)
    rows = _load_rows(workspace_id=workspace_id, parse_run_id=parse_run.id, parsing_repository=parsing_repository, limit=25)
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


def _latest_succeeded_parse_run(*, workspace_id: UUID, upload_id: UUID, parsing_repository: UploadParsingRepository):
    parse_runs = parsing_repository.list_runs(workspace_id=workspace_id, upload_id=upload_id)
    parse_run = next((run for run in parse_runs if run.status == UploadParseStatus.SUCCEEDED), None)
    if parse_run is None:
        raise ApiError(code="PARSE_RUN_NOT_FOUND", message="Account import requires a succeeded parse run.", status_code=409)
    return parse_run


def _load_rows(*, workspace_id: UUID, parse_run_id: UUID, parsing_repository: UploadParsingRepository, limit: int | None = None) -> list[ParsedUploadRow]:
    rows: list[ParsedUploadRow] = []
    page = 1
    while True:
        page_rows, total = parsing_repository.list_rows(workspace_id=workspace_id, parse_run_id=parse_run_id, page=page, page_size=500)
        rows.extend(page_rows)
        if limit and len(rows) >= limit:
            return rows[:limit]
        if len(rows) >= total:
            return rows
        page += 1


def _require_import(*, workspace_id: UUID, account_import_id: UUID, repository: AccountImportRepository):
    import_record = repository.get_import(workspace_id=workspace_id, account_import_id=account_import_id)
    if import_record is None:
        raise ApiError(code="ACCOUNT_IMPORT_NOT_FOUND", message="Account import was not found.", status_code=404)
    return import_record
