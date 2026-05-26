from uuid import UUID

from fastapi import APIRouter, Depends, status

from apps.api.app.core.auth import (
    PRODUCT_PROFILE_READ_ROLES,
    PRODUCT_PROFILE_WRITE_ROLES,
    WorkspacePrincipal,
    require_workspace_member,
)
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.schemas.envelope import success_response
from apps.api.app.schemas.product_profiles import ProductProfileCreate, ProductProfileUpdate

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
