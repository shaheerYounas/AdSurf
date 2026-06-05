from decimal import Decimal
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
from apps.api.app.services.ai_recommendation_brain import AI_RECOMMENDATION_AGENT_NAME

router = APIRouter()

RECOMMENDATION_DECISION_ROLES = {
    WorkspaceRole.OWNER,
    WorkspaceRole.ADMIN,
    WorkspaceRole.ANALYST,
    WorkspaceRole.APPROVER,
}

ACTION_RECOMMENDATION_TYPES = {
    "increase_bid",
    "decrease_bid",
    "add_negative_exact",
    "add_negative_phrase",
    "move_to_exact",
    "pause_review",
}
NON_ACTION_INSIGHT_TYPES = {"keep_running", "watch_lock"}
DATA_QUALITY_TYPES = {"data_quality_review", "data_quality_warning"}
BUDGET_REVIEW_TYPES = {"budget_review"}


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

    existing_import = monitoring_repository.get_import_for_upload(
        workspace_id=workspace_id,
        product_id=product_id,
        upload_id=upload.id,
        report_type="sponsored_products_search_term",
    )
    if existing_import is not None:
        audit_repository.record(
            workspace_id=workspace_id,
            actor_user_id=principal.user_id,
            action="monitoring_import.duplicate_reused",
            entity_type="monitoring_import",
            entity_id=existing_import.id,
            details={
                "upload_id": str(upload.id),
                "parse_run_id": str(parse_run.id),
                "already_imported": True,
                "execution_boundary": "no_live_amazon_change",
            },
        )
        response = MonitoringImportResponse(
            import_record=existing_import,
            job_id=None,
            already_imported=True,
            message="This upload was already imported. View the existing import or explicitly re-run analysis.",
        )
        return success_response(data=response.model_dump(mode="json"))

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
    response = MonitoringImportResponse(import_record=import_record, job_id=job.id, already_imported=False)
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
    # Fetch all data concurrently for speed
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        imports_future = pool.submit(monitoring_repository.list_imports, workspace_id=workspace_id, product_id=product_id)
        recommendations_future = pool.submit(monitoring_repository.list_recommendations, workspace_id=workspace_id, product_id=product_id)
        ai_brain_future = pool.submit(monitoring_repository.list_ai_runs, workspace_id=workspace_id, product_id=product_id, agent_name=AI_RECOMMENDATION_AGENT_NAME, limit=1)
        product_summaries_future = pool.submit(monitoring_repository.list_ai_runs, workspace_id=workspace_id, product_id=product_id, agent_name="stakeholder_reporting_agent", limit=1)
        imports = imports_future.result()
        recommendations = recommendations_future.result()
        ai_brain_runs = ai_brain_future.result()
        product_summaries = product_summaries_future.result()
    latest_import = imports[0] if imports else None
    snapshots = (
        monitoring_repository.list_snapshots(workspace_id=workspace_id, product_id=product_id, monitoring_import_id=latest_import.id)
        if latest_import
        else []
    )
    latest_summary = ai_brain_runs[0] if ai_brain_runs and ai_brain_runs[0].status == "succeeded" else product_summaries[0] if product_summaries else None
    counts: dict[str, int] = {}
    for recommendation in recommendations:
        counts[recommendation.status.value] = counts.get(recommendation.status.value, 0) + 1
        counts[recommendation.recommendation_type.value] = counts.get(recommendation.recommendation_type.value, 0) + 1
    detected_product_groups = _detected_product_groups(snapshots)
    summary = MonitoringSummary(
        imports=imports[:10],
        recommendation_counts=counts,
        top_recommendations=recommendations[:10],
        agent_summary=_dashboard_summary_from_ai_run(latest_summary) if latest_summary else None,
        summary_metrics=_summary_metrics(
            latest_import=latest_import,
            snapshots=snapshots,
            recommendations=recommendations,
            detected_product_groups=detected_product_groups,
        ),
        action_recommendation_counts=_counts_for(recommendations, ACTION_RECOMMENDATION_TYPES),
        non_action_insight_counts=_counts_for(recommendations, NON_ACTION_INSIGHT_TYPES),
        issue_counts=_issue_counts(latest_import.data_quality_warnings_json if latest_import else []),
        detected_product_groups=detected_product_groups,
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
        details={
            "decision_id": str(decision_record.id),
            "note": payload.note.strip(),
            "recommendation_source": recommendation.evidence_json.get("decision_source") or recommendation.explanation_json.get("decision_source"),
            "ai_provider": recommendation.evidence_json.get("ai_provider") or recommendation.explanation_json.get("ai_provider"),
            "ai_model": recommendation.evidence_json.get("ai_model") or recommendation.explanation_json.get("ai_model"),
            "approval_updates_app_state_only": True,
            "execution_boundary": "no_live_amazon_change",
        },
    )
    return success_response(data=recommendation.model_dump(mode="json"))


def _dashboard_summary_from_ai_run(ai_run) -> dict:
    output = ai_run.output_json
    summary = output.get("dashboard_summary") if isinstance(output, dict) else None
    if isinstance(summary, dict):
        return {
            **summary,
            "stakeholder_note": "AI generated recommendation decisions from uploaded report evidence. No live Amazon Ads change was executed.",
            "next_step": "Review pending recommendations and approve or reject with notes.",
            "ai_provider": ai_run.provider,
            "ai_model": ai_run.model,
            "ai_schema_version": ai_run.schema_version,
        }
    return output


def _counts_for(recommendations, recommendation_types: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for recommendation in recommendations:
        rec_type = recommendation.recommendation_type.value
        if rec_type in recommendation_types:
            counts[rec_type] = counts.get(rec_type, 0) + 1
    return counts


def _issue_counts(messages: list[dict]) -> dict[str, int]:
    counts = {"info": 0, "warning": 0, "error": 0, "critical": 0}
    for message in messages:
        severity = str(message.get("severity") or _severity_from_legacy_label(message.get("risk_label"))).lower()
        if severity not in counts:
            severity = "warning"
        counts[severity] += 1
    return counts


def _severity_from_legacy_label(label: object) -> str:
    label_text = str(label or "").lower()
    if label_text == "high_risk":
        return "critical"
    if label_text in {"not_enough_data", "possible_duplicate", "possible_asin_targeting"}:
        return "info"
    if label_text == "safe":
        return "info"
    return "warning"


def _summary_metrics(*, latest_import, snapshots, recommendations, detected_product_groups: list[dict]) -> dict:
    total_spend = sum((snapshot.spend for snapshot in snapshots), Decimal("0"))
    total_sales = sum((snapshot.sales for snapshot in snapshots), Decimal("0"))
    total_orders = sum(snapshot.orders for snapshot in snapshots)
    total_clicks = sum(snapshot.clicks for snapshot in snapshots)
    total_impressions = sum(snapshot.impressions for snapshot in snapshots)
    zero_order_spend = sum((snapshot.spend for snapshot in snapshots if snapshot.orders == 0), Decimal("0"))
    pending = sum(1 for item in recommendations if item.status.value == "pending_approval")
    actionable = sum(1 for item in recommendations if item.recommendation_type.value in ACTION_RECOMMENDATION_TYPES)
    watch = sum(1 for item in recommendations if item.recommendation_type.value in NON_ACTION_INSIGHT_TYPES)
    data_quality = sum(1 for item in recommendations if item.recommendation_type.value in DATA_QUALITY_TYPES)
    budget = sum(1 for item in recommendations if item.recommendation_type.value in BUDGET_REVIEW_TYPES)
    return {
        "rows_analyzed": latest_import.processed_rows if latest_import else len(snapshots),
        "report_rows": latest_import.total_rows if latest_import else len(snapshots),
        "recommendations_generated": len(recommendations),
        "pending_human_review": pending,
        "actionable_recommendations": actionable,
        "watch_insights": watch,
        "data_quality_checks": data_quality,
        "budget_review_notes": budget,
        "total_spend": _money_str(total_spend),
        "total_sales": _money_str(total_sales),
        "total_orders": total_orders,
        "total_clicks": total_clicks,
        "total_impressions": total_impressions,
        "overall_acos": _rate_str(total_spend / total_sales) if total_sales > 0 else None,
        "zero_order_spend": _money_str(zero_order_spend),
        "detected_products": len(detected_product_groups),
        "no_live_amazon_changes": True,
        "manual_export_required": True,
    }


def _detected_product_groups(snapshots) -> list[dict]:
    groups: dict[str, dict] = {}
    for snapshot in snapshots:
        identifiers = _product_identifiers_from_raw(snapshot.raw_metrics_json)
        key = identifiers.get("asin") or identifiers.get("sku")
        if not key:
            continue
        group = groups.setdefault(
            key,
            {
                "key": key,
                "asin": identifiers.get("asin"),
                "sku": identifiers.get("sku"),
                "rows": 0,
                "spend": Decimal("0"),
                "sales": Decimal("0"),
                "orders": 0,
                "campaigns": set(),
                "source": identifiers.get("source"),
            },
        )
        group["rows"] += 1
        group["spend"] += snapshot.spend
        group["sales"] += snapshot.sales
        group["orders"] += snapshot.orders
        group["campaigns"].add(snapshot.campaign_name)
    output = []
    for group in sorted(groups.values(), key=lambda item: item["spend"], reverse=True):
        output.append(
            {
                "key": group["key"],
                "asin": group["asin"],
                "sku": group["sku"],
                "rows": group["rows"],
                "spend": _money_str(group["spend"]),
                "sales": _money_str(group["sales"]),
                "orders": group["orders"],
                "campaign_count": len(group["campaigns"]),
                "source": group["source"],
            }
        )
    return output


def _product_identifiers_from_raw(row: dict) -> dict[str, str | None]:
    normalized = {_normalize_header(key): value for key, value in row.items()}
    for asin_key in ("advertised asin", "advertised asin  asin", "campaign owned asin", "asin"):
        asin = _clean_identifier(normalized.get(asin_key))
        if asin:
            return {"asin": asin.upper(), "sku": _clean_identifier(normalized.get("advertised sku") or normalized.get("sku")), "source": asin_key}
    for sku_key in ("advertised sku", "sku"):
        sku = _clean_identifier(normalized.get(sku_key))
        if sku:
            return {"asin": None, "sku": sku, "source": sku_key}
    return {"asin": None, "sku": None, "source": None}


def _clean_identifier(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_header(value: object) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def _money_str(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))


def _rate_str(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))
