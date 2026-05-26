from uuid import uuid4

from apps.api.app.repositories.product_profiles import LocalProductProfileRepository
from apps.api.app.schemas.product_profiles import ProductProfileCreate, ProductProfileUpdate


def test_local_repository_persists_product_profiles_by_workspace() -> None:
    repository = LocalProductProfileRepository()
    workspace_id = uuid4()

    created = repository.create(
        workspace_id=workspace_id,
        payload=ProductProfileCreate(product_name="Vinyl Tool"),
        actor_user_id="local-user",
    )

    assert repository.get(workspace_id=workspace_id, product_id=created.id) == created
    assert repository.list(workspace_id=workspace_id) == [created]


def test_local_repository_does_not_return_cross_workspace_products() -> None:
    repository = LocalProductProfileRepository()
    workspace_id = uuid4()
    other_workspace_id = uuid4()

    created = repository.create(
        workspace_id=workspace_id,
        payload=ProductProfileCreate(product_name="Vinyl Tool"),
        actor_user_id="local-user",
    )

    assert repository.get(workspace_id=other_workspace_id, product_id=created.id) is None
    assert repository.list(workspace_id=other_workspace_id) == []


def test_local_repository_update_is_workspace_scoped() -> None:
    repository = LocalProductProfileRepository()
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    created = repository.create(
        workspace_id=workspace_id,
        payload=ProductProfileCreate(product_name="Vinyl Tool"),
        actor_user_id="local-user",
    )

    blocked = repository.update(
        workspace_id=other_workspace_id,
        product_id=created.id,
        payload=ProductProfileUpdate(product_name="Blocked"),
        actor_user_id="local-user",
    )
    updated = repository.update(
        workspace_id=workspace_id,
        product_id=created.id,
        payload=ProductProfileUpdate(product_name="Updated"),
        actor_user_id="local-user",
    )

    assert blocked is None
    assert updated is not None
    assert updated.product_name == "Updated"
