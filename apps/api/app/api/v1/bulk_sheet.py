"""Amazon Bulk Operations sheet import API.

POST /v1/workspaces/{workspace_id}/bulk-sheet/parse
  — Upload a bulk sheet XLSX/CSV and receive a structured account snapshot.
    Nothing is persisted; this is a stateless parse-and-return endpoint so the
    frontend can render the account structure immediately.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status

from apps.api.app.core.auth import PRODUCT_PROFILE_READ_ROLES, WorkspacePrincipal, require_workspace_member
from uuid import UUID
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.bulk_sheet import (
    BulkAdGroupSchema,
    BulkCampaignSchema,
    BulkKeywordSchema,
    BulkNegativeKeywordSchema,
    BulkProductAdSchema,
    BulkSheetSnapshotResponse,
    BulkSheetStats,
    BulkTargetSchema,
)
from apps.api.app.schemas.envelope import success_response
from apps.api.app.services.bulk_sheet_reader import BulkSheetSnapshot, read_bulk_sheet

router = APIRouter()

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB — bulk sheets can be large


@router.post(
    "/workspaces/{workspace_id}/bulk-sheet/parse",
    status_code=status.HTTP_200_OK,
    summary="Parse an Amazon Bulk Operations XLSX/CSV into an account snapshot",
)
async def parse_bulk_sheet(
    workspace_id: UUID,
    file: UploadFile = File(...),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    content = await file.read()

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise ApiError(
            code="FILE_TOO_LARGE",
            message=f"File exceeds the 20 MB limit ({len(content) // 1_048_576} MB uploaded).",
            status_code=413,
        )

    filename = file.filename or "bulk_sheet.xlsx"
    lower = filename.lower()

    if not (lower.endswith(".xlsx") or lower.endswith(".csv")):
        raise ApiError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Only .xlsx and .csv files are supported for bulk sheet import.",
            status_code=415,
        )

    snapshot = read_bulk_sheet(content, filename)

    if not snapshot.campaigns and not snapshot.ad_groups and not snapshot.keywords:
        raise ApiError(
            code="BULK_SHEET_EMPTY",
            message=(
                "No campaigns, ad groups, or keywords were found in this file. "
                "Please upload a valid Amazon Sponsored Products Bulk Operations export "
                "(File → Download → Bulk Operations)."
            ),
            status_code=422,
            details={
                "filename": filename,
                "warnings": snapshot.warnings,
                "hint": "Make sure the file is a Bulk Operations export, not a Search Term Report or Campaign Manager export.",
            },
        )

    response = _snapshot_to_response(snapshot)
    return success_response(response.model_dump(mode="json"))


def _snapshot_to_response(snap: BulkSheetSnapshot) -> BulkSheetSnapshotResponse:
    return BulkSheetSnapshotResponse(
        filename=snap.filename,
        date_range_start=snap.date_range_start,
        date_range_end=snap.date_range_end,
        account_id=snap.account_id,
        stats=BulkSheetStats(
            total_campaigns=len(snap.campaigns),
            active_campaigns=snap.active_campaigns,
            total_ad_groups=len(snap.ad_groups),
            total_keywords=len(snap.keywords),
            total_targets=len(snap.targets),
            total_product_ads=len(snap.product_ads),
            total_negative_keywords=len(snap.negative_keywords),
        ),
        campaigns=[
            BulkCampaignSchema(
                campaign_id=c.campaign_id,
                name=c.name,
                status=c.status,
                daily_budget=c.daily_budget,
                targeting_type=c.targeting_type,
                start_date=c.start_date,
                end_date=c.end_date,
                bidding_strategy=c.bidding_strategy,
            )
            for c in snap.campaigns
        ],
        ad_groups=[
            BulkAdGroupSchema(
                ad_group_id=ag.ad_group_id,
                campaign_id=ag.campaign_id,
                campaign_name=ag.campaign_name,
                name=ag.name,
                status=ag.status,
                default_bid=ag.default_bid,
            )
            for ag in snap.ad_groups
        ],
        keywords=[
            BulkKeywordSchema(
                keyword_id=kw.keyword_id,
                campaign_id=kw.campaign_id,
                campaign_name=kw.campaign_name,
                ad_group_id=kw.ad_group_id,
                ad_group_name=kw.ad_group_name,
                keyword_text=kw.keyword_text,
                match_type=kw.match_type,
                bid=kw.bid,
                status=kw.status,
            )
            for kw in snap.keywords
        ],
        targets=[
            BulkTargetSchema(
                target_id=t.target_id,
                campaign_id=t.campaign_id,
                campaign_name=t.campaign_name,
                ad_group_id=t.ad_group_id,
                ad_group_name=t.ad_group_name,
                expression=t.expression,
                bid=t.bid,
                status=t.status,
            )
            for t in snap.targets
        ],
        negative_keywords=[
            BulkNegativeKeywordSchema(
                campaign_id=nk.campaign_id,
                campaign_name=nk.campaign_name,
                ad_group_id=nk.ad_group_id,
                ad_group_name=nk.ad_group_name,
                keyword_text=nk.keyword_text,
                match_type=nk.match_type,
            )
            for nk in snap.negative_keywords
        ],
        product_ads=[
            BulkProductAdSchema(
                ad_id=ad.ad_id,
                campaign_id=ad.campaign_id,
                campaign_name=ad.campaign_name,
                ad_group_id=ad.ad_group_id,
                ad_group_name=ad.ad_group_name,
                asin=ad.asin,
                sku=ad.sku,
                status=ad.status,
            )
            for ad in snap.product_ads
        ],
        warnings=snap.warnings,
    )
