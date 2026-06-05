import json
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import text

from apps.api.app.core.auth import (
    PRODUCT_PROFILE_READ_ROLES,
    PRODUCT_PROFILE_WRITE_ROLES,
    WorkspacePrincipal,
    require_workspace_member,
)
from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.repositories.monitoring import MonitoringRepository, get_monitoring_repository
from apps.api.app.repositories.uploads import UploadRepository, get_upload_repository
from apps.api.app.schemas.envelope import success_response
from apps.api.app.schemas.product_profiles import ProductProfileCreate, ProductProfileUpdate, BulkDeleteRequest

router = APIRouter()


@router.post(
    "/workspaces/{workspace_id}/products",
    status_code=status.HTTP_201_CREATED,
)
def create_product_profile(
    workspace_id: UUID,
    payload: ProductProfileCreate,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    product = repository.create(workspace_id=workspace_id, payload=payload, actor_user_id=principal.user_id)
    return success_response(data=product.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/products")
def list_product_profiles(
    workspace_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    products = repository.list(workspace_id=workspace_id)
    return success_response(
        data=[product.model_dump(mode="json") for product in products],
        meta={"total": len(products), "page": 1, "page_size": len(products), "has_next": False},
    )


@router.get("/workspaces/{workspace_id}/dashboard-summary")
def get_dashboard_summary(
    workspace_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    monitoring_repository: MonitoringRepository = Depends(get_monitoring_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    database_url = get_settings().database_url
    if database_url and database_url.startswith("sqlite"):
        return success_response(data=_sqlite_dashboard_summary(workspace_id=workspace_id))
    if database_url:
        return success_response(data=_postgres_dashboard_summary(workspace_id=workspace_id))
    products = product_repository.list(workspace_id=workspace_id)
    uploads, upload_total = upload_repository.list(workspace_id=workspace_id, product_id=None, status=None, page=1, page_size=1000)
    recommendations = monitoring_repository.list_recommendations(workspace_id=workspace_id, limit=50)
    upload_counts: dict[str, int] = {}
    for upload in uploads:
        upload_counts[upload.status.value] = upload_counts.get(upload.status.value, 0) + 1
    recommendation_counts: dict[str, int] = {}
    for recommendation in recommendations:
        recommendation_counts[recommendation.status.value] = recommendation_counts.get(recommendation.status.value, 0) + 1
        recommendation_counts[recommendation.recommendation_type.value] = recommendation_counts.get(recommendation.recommendation_type.value, 0) + 1
    return success_response(
        data={
            "products": [product.model_dump(mode="json") for product in products[:6]],
            "product_count": len(products),
            "upload_count": upload_total,
            "upload_counts": upload_counts,
            "pending_recommendation_count": recommendation_counts.get("pending_approval", 0) + recommendation_counts.get("pending", 0),
            "recommendation_counts": recommendation_counts,
            "top_recommendations": [recommendation.model_dump(mode="json") for recommendation in recommendations[:5]],
        }
    )


def _postgres_dashboard_summary(*, workspace_id: UUID) -> dict:
    with get_database_engine().begin() as connection:
        row = connection.execute(
            text(
                """
                with products_limited as (
                    select id, workspace_id, product_name, asin, sku, marketplace, currency,
                        target_acos, default_budget, default_bid, status, created_at, updated_at
                    from product_profiles
                    where workspace_id = :workspace_id
                    order by created_at desc
                    limit 6
                ),
                product_count as (
                    select count(*) as total
                    from product_profiles
                    where workspace_id = :workspace_id
                ),
                upload_count_groups as (
                    select status::text as status, count(*) as total
                    from uploads
                    where workspace_id = :workspace_id
                    group by status::text
                ),
                upload_summary as (
                    select
                        coalesce(jsonb_object_agg(status, total), '{}'::jsonb) as upload_counts,
                        coalesce(sum(total), 0) as upload_count
                    from upload_count_groups
                ),
                recommendation_count_groups as (
                    select status::text as summary_key, count(*) as total
                    from recommendations
                    where workspace_id = :workspace_id
                    group by status::text
                    union all
                    select recommendation_type::text as summary_key, count(*) as total
                    from recommendations
                    where workspace_id = :workspace_id
                    group by recommendation_type::text
                ),
                recommendation_summary as (
                    select coalesce(jsonb_object_agg(summary_key, total), '{}'::jsonb) as recommendation_counts
                    from recommendation_count_groups
                ),
                pending_recommendations as (
                    select count(*) as total
                    from recommendations
                    where workspace_id = :workspace_id
                        and status::text in ('pending_approval', 'pending')
                ),
                top_recommendations as (
                    select id, product_id, recommendation_type::text as recommendation_type, status::text as status,
                        priority::text as priority, rule_name, campaign_name, ad_group_name, targeting,
                        customer_search_term, created_at
                    from recommendations
                    where workspace_id = :workspace_id
                    order by case priority::text when 'critical' then 0 when 'high' then 1 when 'medium' then 2 else 3 end,
                        created_at desc
                    limit 5
                )
                select
                    coalesce((select jsonb_agg(to_jsonb(products_limited)) from products_limited), '[]'::jsonb) as products,
                    (select total from product_count) as product_count,
                    (select upload_count from upload_summary) as upload_count,
                    (select upload_counts from upload_summary) as upload_counts,
                    (select total from pending_recommendations) as pending_recommendation_count,
                    (select recommendation_counts from recommendation_summary) as recommendation_counts,
                    coalesce((select jsonb_agg(to_jsonb(top_recommendations)) from top_recommendations), '[]'::jsonb) as top_recommendations
                """
            ),
            {"workspace_id": workspace_id},
        ).mappings().one()

    products = _json_value(row["products"], [])
    upload_counts = {key: int(value) for key, value in _json_value(row["upload_counts"], {}).items()}
    recommendation_counts = {key: int(value) for key, value in _json_value(row["recommendation_counts"], {}).items()}
    recommendation_rows = _json_value(row["top_recommendations"], [])
    return {
        "products": products,
        "product_count": int(row["product_count"]),
        "upload_count": int(row["upload_count"]),
        "upload_counts": upload_counts,
        "pending_recommendation_count": int(row["pending_recommendation_count"]),
        "recommendation_counts": recommendation_counts,
        "top_recommendations": [_dashboard_recommendation(row) for row in recommendation_rows],
    }


def _sqlite_dashboard_summary(*, workspace_id: UUID) -> dict:
    with get_database_engine().begin() as connection:
        product_rows = connection.execute(
            text(
                """
                select id, workspace_id, product_name, asin, sku, marketplace, currency,
                    target_acos, default_budget, default_bid, status, created_at, updated_at
                from product_profiles
                where workspace_id = :workspace_id
                order by created_at desc
                limit 6
                """
            ),
            {"workspace_id": workspace_id},
        ).mappings().all()
        product_count = connection.execute(
            text("select count(*) from product_profiles where workspace_id = :workspace_id"),
            {"workspace_id": workspace_id},
        ).scalar_one()
        upload_rows = connection.execute(
            text(
                """
                select status, count(*) as total
                from uploads
                where workspace_id = :workspace_id
                group by status
                """
            ),
            {"workspace_id": workspace_id},
        ).mappings().all()
        recommendation_rows = connection.execute(
            text(
                """
                select status as summary_key, count(*) as total
                from recommendations
                where workspace_id = :workspace_id
                group by status
                union all
                select recommendation_type as summary_key, count(*) as total
                from recommendations
                where workspace_id = :workspace_id
                group by recommendation_type
                """
            ),
            {"workspace_id": workspace_id},
        ).mappings().all()
        pending_recommendation_count = connection.execute(
            text(
                """
                select count(*)
                from recommendations
                where workspace_id = :workspace_id
                    and status in ('pending_approval', 'pending')
                """
            ),
            {"workspace_id": workspace_id},
        ).scalar_one()
        top_recommendation_rows = connection.execute(
            text(
                """
                select id, product_id, recommendation_type, status, priority, rule_name,
                    campaign_name, ad_group_name, targeting, customer_search_term, created_at
                from recommendations
                where workspace_id = :workspace_id
                order by case priority when 'critical' then 0 when 'high' then 1 when 'medium' then 2 else 3 end,
                    created_at desc
                limit 5
                """
            ),
            {"workspace_id": workspace_id},
        ).mappings().all()

    upload_counts = {row["status"]: int(row["total"]) for row in upload_rows}
    recommendation_counts = {row["summary_key"]: int(row["total"]) for row in recommendation_rows}
    return {
        "products": [_dashboard_product(row) for row in product_rows],
        "product_count": int(product_count),
        "upload_count": sum(upload_counts.values()),
        "upload_counts": upload_counts,
        "pending_recommendation_count": int(pending_recommendation_count),
        "recommendation_counts": recommendation_counts,
        "top_recommendations": [_dashboard_recommendation(row) for row in top_recommendation_rows],
    }


def _json_value(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, str):
        return json.loads(value)
    return value


def _dashboard_product(row) -> dict:
    return {
        **dict(row),
        "target_acos": f"{float(row['target_acos']):.4f}",
        "default_budget": f"{float(row['default_budget']):.4f}",
        "default_bid": f"{float(row['default_bid']):.4f}",
    }


def _dashboard_recommendation(row) -> dict:
    return {
        **dict(row),
        "entity_type": "search_term",
        "confidence": "medium",
        "input_metrics_json": {},
        "current_metric_snapshot_json": {},
        "evidence_json": {},
        "proposed_action_json": {},
        "explanation_json": {"summary": "Open the recommendation queue to review evidence and approve or reject."},
    }


@router.get("/workspaces/{workspace_id}/products/{product_id}")
def get_product_profile(
    workspace_id: UUID,
    product_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    product = repository.get(workspace_id=workspace_id, product_id=product_id)
    if product is None:
        raise ApiError(code="PRODUCT_NOT_FOUND", message="Product profile was not found.", status_code=404)
    return success_response(data=product.model_dump(mode="json"))


@router.patch("/workspaces/{workspace_id}/products/{product_id}")
def update_product_profile(
    workspace_id: UUID,
    product_id: UUID,
    payload: ProductProfileUpdate,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    product = repository.update(
        workspace_id=workspace_id,
        product_id=product_id,
        payload=payload,
        actor_user_id=principal.user_id,
    )
    if product is None:
        raise ApiError(code="PRODUCT_NOT_FOUND", message="Product profile was not found.", status_code=404)
    return success_response(data=product.model_dump(mode="json"))


@router.delete(
    "/workspaces/{workspace_id}/products/{product_id}",
    status_code=status.HTTP_200_OK,
)
def delete_product_profile(
    workspace_id: UUID,
    product_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    deleted = repository.delete(workspace_id=workspace_id, product_id=product_id)
    if not deleted:
        raise ApiError(code="PRODUCT_NOT_FOUND", message="Product profile was not found.", status_code=404)
    return success_response(data={"deleted": True, "product_id": str(product_id)})


@router.post(
    "/workspaces/{workspace_id}/products/bulk-delete",
    status_code=status.HTTP_200_OK,
)
def bulk_delete_product_profiles(
    workspace_id: UUID,
    payload: BulkDeleteRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)
    deleted_count = repository.bulk_delete(workspace_id=workspace_id, product_ids=payload.product_ids)
    return success_response(data={"deleted_count": deleted_count})
