from dataclasses import dataclass
import logging
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.orchestration.graph_state import initial_state
from apps.api.app.repositories.account_imports import AccountImportRepository, new_account_import
from apps.api.app.repositories.product_profiles import ProductProfileRepository
from apps.api.app.repositories.upload_parsing import UploadParsingRepository
from apps.api.app.repositories.uploads import UploadRepository
from apps.api.app.repositories.workflows import WorkflowRepository, new_workflow
from apps.api.app.schemas.account_imports import AccountImport, AccountImportStatus
from apps.api.app.schemas.upload_parsing import ParsedUploadRow, UploadParseStatus
from apps.api.app.schemas.uploads import UploadStatus
from apps.api.app.schemas.workflows import AgentWorkflow
from apps.api.app.services.product_entity_resolver import ProductEntityResolution, ProductEntityResolver
from apps.api.app.services.report_type_detector import ReportDetectionResult, ReportTypeDetector
from apps.api.app.services.amazon_ads_safeguards import analyze_search_term_report_rows


@dataclass(frozen=True)
class AccountImportBuildResult:
    import_record: AccountImport
    detection: ReportDetectionResult
    resolution: ProductEntityResolution
    workflow: AgentWorkflow


def create_account_import_from_processed_upload(
    *,
    workspace_id: UUID,
    upload_id: UUID,
    actor_user_id: str,
    upload_repository: UploadRepository,
    parsing_repository: UploadParsingRepository,
    product_repository: ProductProfileRepository,
    account_import_repository: AccountImportRepository,
    workflow_repository: WorkflowRepository,
) -> AccountImportBuildResult:
    logging.info("Creating account import for workspace %s using upload %s", workspace_id, upload_id)
    upload = upload_repository.get(workspace_id=workspace_id, upload_id=upload_id)
    if upload is None:
        raise ApiError(code="UPLOAD_NOT_FOUND", message="Upload was not found.", status_code=404)
    if upload.status != UploadStatus.PROCESSED:
        raise ApiError(code="UPLOAD_NOT_PROCESSED", message="Account import requires a processed upload.", status_code=409)

    parse_run = latest_succeeded_parse_run(workspace_id=workspace_id, upload_id=upload.id, parsing_repository=parsing_repository)
    rows = load_rows(workspace_id=workspace_id, parse_run_id=parse_run.id, parsing_repository=parsing_repository)
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
    safeguard_rows = [{**row.row_data_json, "_row_number": row.row_number} for row in rows]
    safeguards = analyze_search_term_report_rows(rows=safeguard_rows, detection=detection)
    warnings.extend(safeguards.warnings)

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
        created_by=actor_user_id,
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

    workflow_state = initial_state(
        workflow_id="pending",
        workspace_id=str(workspace_id),
        account_import_id=str(import_record.id),
        upload_id=str(upload.id),
    )
    workflow = workflow_repository.create_workflow(
        workflow=new_workflow(
            workspace_id=workspace_id,
            account_import_id=import_record.id,
            upload_id=upload.id,
            created_by=actor_user_id,
            state_json={**workflow_state, "workflow_id": "pending"},
        )
    )
    workflow_repository.update_workflow(
        workflow_id=workflow.id,
        workspace_id=workspace_id,
        status=workflow.status,
        current_node=workflow.current_node,
        state_json={**workflow.state_json, "workflow_id": str(workflow.id)},
    )
    refreshed = workflow_repository.get_workflow(workspace_id=workspace_id, workflow_id=workflow.id) or workflow
    return AccountImportBuildResult(import_record=import_record, detection=detection, resolution=resolution, workflow=refreshed)


def latest_succeeded_parse_run(*, workspace_id: UUID, upload_id: UUID, parsing_repository: UploadParsingRepository):
    parse_runs = parsing_repository.list_runs(workspace_id=workspace_id, upload_id=upload_id)
    parse_run = next((run for run in parse_runs if run.status == UploadParseStatus.SUCCEEDED), None)
    if parse_run is None:
        raise ApiError(code="PARSE_RUN_NOT_FOUND", message="Account import requires a succeeded parse run.", status_code=409)
    return parse_run


def load_rows(*, workspace_id: UUID, parse_run_id: UUID, parsing_repository: UploadParsingRepository, limit: int | None = None) -> list[ParsedUploadRow]:
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
