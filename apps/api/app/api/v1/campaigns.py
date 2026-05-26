from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from apps.api.app.core.auth import PRODUCT_PROFILE_READ_ROLES, PRODUCT_PROFILE_WRITE_ROLES, WorkspacePrincipal, require_workspace_member
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.campaigns import CampaignRepository, get_campaign_repository, new_bulk_export, new_campaign_plan
from apps.api.app.repositories.keyword_review import KeywordReviewRepository, get_keyword_review_repository
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.schemas.campaigns import BulkExportCreateRequest, BulkExportResponse, CampaignPlanApproveRequest, CampaignPlanCreateRequest, CampaignPlanStatus
from apps.api.app.schemas.envelope import success_response
from apps.api.app.services.campaign_generation import build_bulk_export_rows, build_campaign_plan_json, render_bulk_export_csv
from apps.api.app.services.storage import StorageService, get_storage_service

router = APIRouter()


@router.post("/workspaces/{workspace_id}/products/{product_id}/campaign-plans")
def create_campaign_plan(
    workspace_id: UUID,
    product_id: UUID,
    payload: CampaignPlanCreateRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
    review_repository: KeywordReviewRepository = Depends(get_keyword_review_repository),
    campaign_repository: CampaignRepository = Depends(get_campaign_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    product = product_repository.get(workspace_id=workspace_id, product_id=product_id)
    if product is None:
        raise ApiError(code="PRODUCT_NOT_FOUND", message="Product profile was not found.", status_code=404)
    keyword_set = review_repository.get_keyword_set(workspace_id=workspace_id, keyword_set_id=payload.approved_keyword_set_id)
    if keyword_set is None or keyword_set.product_id != product_id:
        raise ApiError(code="APPROVED_KEYWORD_SET_NOT_FOUND", message="Approved keyword set was not found.", status_code=404)
    items, total = review_repository.list_keyword_set_items(workspace_id=workspace_id, keyword_set_id=keyword_set.id, page=1, page_size=1000)
    if total == 0:
        raise ApiError(code="CAMPAIGN_PLAN_EMPTY_KEYWORD_SET", message="Campaign generation requires at least one approved keyword.", status_code=409)
    plan_json = build_campaign_plan_json(product=product, keyword_set_id=keyword_set.id, items=items)
    plan = new_campaign_plan(
        workspace_id=workspace_id,
        product_id=product_id,
        approved_keyword_set_id=keyword_set.id,
        version=campaign_repository.next_plan_version(workspace_id=workspace_id, product_id=product_id),
        plan_json=plan_json,
        created_by=principal.user_id,
    )
    created = campaign_repository.create_plan(plan=plan)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="campaign_plan.generated",
        entity_type="campaign_plan",
        entity_id=created.id,
        details={"approved_keyword_set_id": str(keyword_set.id), "keyword_count": total, "rule_version_id": created.rule_version_id},
    )
    return success_response(data=created.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/campaign-plans/{plan_id}")
def get_campaign_plan(
    workspace_id: UUID,
    plan_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    campaign_repository: CampaignRepository = Depends(get_campaign_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    plan = campaign_repository.get_plan(workspace_id=workspace_id, plan_id=plan_id)
    if plan is None:
        raise ApiError(code="CAMPAIGN_PLAN_NOT_FOUND", message="Campaign plan was not found.", status_code=404)
    return success_response(data=plan.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/campaign-plans/{plan_id}/approve")
def approve_campaign_plan(
    workspace_id: UUID,
    plan_id: UUID,
    payload: CampaignPlanApproveRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    campaign_repository: CampaignRepository = Depends(get_campaign_repository),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    plan = campaign_repository.approve_plan(
        workspace_id=workspace_id,
        plan_id=plan_id,
        actor_user_id=principal.user_id,
        approval_note=payload.approval_note,
    )
    if plan is None:
        raise ApiError(code="CAMPAIGN_PLAN_NOT_APPROVABLE", message="Campaign plan was not found or cannot be approved.", status_code=409)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="campaign_plan.approved",
        entity_type="campaign_plan",
        entity_id=plan.id,
        details={"approval_note": payload.approval_note.strip()},
    )
    return success_response(data=plan.model_dump(mode="json"))


@router.post("/workspaces/{workspace_id}/campaign-plans/{plan_id}/exports")
def create_bulk_export(
    workspace_id: UUID,
    plan_id: UUID,
    payload: BulkExportCreateRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    campaign_repository: CampaignRepository = Depends(get_campaign_repository),
    storage_service: StorageService = Depends(get_storage_service),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    plan = campaign_repository.get_plan(workspace_id=workspace_id, plan_id=plan_id)
    if plan is None:
        raise ApiError(code="CAMPAIGN_PLAN_NOT_FOUND", message="Campaign plan was not found.", status_code=404)
    if plan.status != CampaignPlanStatus.APPROVED:
        raise ApiError(code="CAMPAIGN_PLAN_APPROVAL_REQUIRED", message="Campaign plan must be approved before export.", status_code=409)
    rows = build_bulk_export_rows(plan_json=plan.plan_json)
    if not rows:
        raise ApiError(code="BULK_EXPORT_EMPTY", message="Bulk export generated no rows.", status_code=409)
    filename = "bulk.csv"
    storage_path = f"/workspaces/{workspace_id}/products/{plan.product_id}/exports/{plan.id}/{filename}"
    export = new_bulk_export(
        workspace_id=workspace_id,
        product_id=plan.product_id,
        campaign_plan_id=plan.id,
        storage_path=storage_path,
        original_filename=filename,
        rows_json=rows,
        approved_by=principal.user_id,
        approval_note=payload.approval_note,
    )
    storage_service.write_upload_object(storage_path=export.storage_path, content=render_bulk_export_csv(rows))
    created = campaign_repository.create_export(export=export)
    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="bulk_export.approved",
        entity_type="bulk_export",
        entity_id=created.id,
        details={"campaign_plan_id": str(plan.id), "approval_note": payload.approval_note.strip(), "row_count": len(rows)},
    )
    response = BulkExportResponse(export=created, download_url=f"/v1/workspaces/{workspace_id}/exports/{created.id}/download")
    return success_response(data=response.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/exports/{export_id}")
def get_bulk_export(
    workspace_id: UUID,
    export_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    campaign_repository: CampaignRepository = Depends(get_campaign_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    export = campaign_repository.get_export(workspace_id=workspace_id, export_id=export_id)
    if export is None:
        raise ApiError(code="BULK_EXPORT_NOT_FOUND", message="Bulk export was not found.", status_code=404)
    response = BulkExportResponse(export=export, download_url=f"/v1/workspaces/{workspace_id}/exports/{export.id}/download")
    return success_response(data=response.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/exports/{export_id}/download")
def download_bulk_export(
    workspace_id: UUID,
    export_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    campaign_repository: CampaignRepository = Depends(get_campaign_repository),
    storage_service: StorageService = Depends(get_storage_service),
) -> Response:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    export = campaign_repository.get_export(workspace_id=workspace_id, export_id=export_id)
    if export is None:
        raise ApiError(code="BULK_EXPORT_NOT_FOUND", message="Bulk export was not found.", status_code=404)
    content = storage_service.read_upload_object(storage_path=export.storage_path)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{export.original_filename}"'},
    )
