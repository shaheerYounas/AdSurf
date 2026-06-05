from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.product_profiles import ProductProfile, ProductProfileCreate, ProductProfileUpdate


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProductProfileRepository(ABC):
    @abstractmethod
    def create(self, workspace_id: UUID, payload: ProductProfileCreate, actor_user_id: str) -> ProductProfile:
        raise NotImplementedError

    @abstractmethod
    def list(self, workspace_id: UUID) -> list[ProductProfile]:
        raise NotImplementedError

    @abstractmethod
    def get(self, workspace_id: UUID, product_id: UUID) -> ProductProfile | None:
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        workspace_id: UUID,
        product_id: UUID,
        payload: ProductProfileUpdate,
        actor_user_id: str,
    ) -> ProductProfile | None:
        raise NotImplementedError


class LocalProductProfileRepository(ProductProfileRepository):
    """Local/test repository used only when DATABASE_URL is absent in local/test."""

    def __init__(self) -> None:
        self._products: dict[UUID, dict[UUID, ProductProfile]] = {}

    def create(self, workspace_id: UUID, payload: ProductProfileCreate, actor_user_id: str) -> ProductProfile:
        now = datetime.now(UTC)
        product = ProductProfile(
            id=uuid4(),
            workspace_id=workspace_id,
            product_name=payload.product_name,
            asin=payload.asin,
            sku=payload.sku,
            marketplace=payload.marketplace,
            currency=payload.currency,
            target_acos=payload.target_acos,
            default_budget=payload.default_budget,
            default_bid=payload.default_bid,
            status=payload.status,
            created_at=now,
            updated_at=now,
        )
        self._products.setdefault(workspace_id, {})[product.id] = product
        return product

    def list(self, workspace_id: UUID) -> list[ProductProfile]:
        return list(self._products.get(workspace_id, {}).values())

    def get(self, workspace_id: UUID, product_id: UUID) -> ProductProfile | None:
        return self._products.get(workspace_id, {}).get(product_id)

    def update(
        self,
        workspace_id: UUID,
        product_id: UUID,
        payload: ProductProfileUpdate,
        actor_user_id: str,
    ) -> ProductProfile | None:
        current = self.get(workspace_id=workspace_id, product_id=product_id)
        if current is None:
            return None
        changes = payload.model_dump(exclude_unset=True)
        updated = current.model_copy(update={**changes, "updated_at": datetime.now(UTC)})
        self._products[workspace_id][product_id] = updated
        return updated


class PostgresProductProfileRepository(ProductProfileRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, workspace_id: UUID, payload: ProductProfileCreate, actor_user_id: str) -> ProductProfile:
        product_id = uuid4()
        now = _now_iso()
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into product_profiles (
                        id, workspace_id, product_name, asin, sku, marketplace, currency,
                        target_acos, default_budget, default_bid, status, created_by, updated_by,
                        created_at, updated_at
                    )
                    values (
                        :id, :workspace_id, :product_name, :asin, :sku, :marketplace, :currency,
                        :target_acos, :default_budget, :default_bid, :status, :created_by, :updated_by,
                        :created_at, :updated_at
                    )
                    returning id, workspace_id, product_name, asin, sku, marketplace, currency,
                        target_acos, default_budget, default_bid, status, created_at, updated_at
                    """
                ),
                {
                    "id": product_id,
                    "workspace_id": workspace_id,
                    "product_name": payload.product_name,
                    "asin": payload.asin,
                    "sku": payload.sku,
                    "marketplace": payload.marketplace,
                    "currency": payload.currency,
                    "target_acos": payload.target_acos,
                    "default_budget": payload.default_budget,
                    "default_bid": payload.default_bid,
                    "status": payload.status.value,
                    "created_by": _uuid_or_none(actor_user_id),
                    "updated_by": _uuid_or_none(actor_user_id),
                    "created_at": now,
                    "updated_at": now,
                },
            ).mappings().one()
        return _product_from_row(row)

    def list(self, workspace_id: UUID) -> list[ProductProfile]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    select id, workspace_id, product_name, asin, sku, marketplace, currency,
                        target_acos, default_budget, default_bid, status, created_at, updated_at
                    from product_profiles
                    where workspace_id = :workspace_id
                    order by created_at desc
                    """
                ),
                {"workspace_id": workspace_id},
            ).mappings().all()
        return [_product_from_row(row) for row in rows]

    def get(self, workspace_id: UUID, product_id: UUID) -> ProductProfile | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    select id, workspace_id, product_name, asin, sku, marketplace, currency,
                        target_acos, default_budget, default_bid, status, created_at, updated_at
                    from product_profiles
                    where workspace_id = :workspace_id and id = :product_id
                    """
                ),
                {"workspace_id": workspace_id, "product_id": product_id},
            ).mappings().first()
        return _product_from_row(row) if row else None

    def update(
        self,
        workspace_id: UUID,
        product_id: UUID,
        payload: ProductProfileUpdate,
        actor_user_id: str,
    ) -> ProductProfile | None:
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return self.get(workspace_id=workspace_id, product_id=product_id)

        now = _now_iso()
        set_clauses = [f"{field} = :{field}" for field in changes]
        set_clauses.extend(["updated_by = :updated_by", "updated_at = :now"])
        params = {
            **{key: _serialize_value(value) for key, value in changes.items()},
            "updated_by": _uuid_or_none(actor_user_id),
            "now": now,
            "workspace_id": workspace_id,
            "product_id": product_id,
        }
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    f"""
                    update product_profiles
                    set {", ".join(set_clauses)}
                    where workspace_id = :workspace_id and id = :product_id
                    returning id, workspace_id, product_name, asin, sku, marketplace, currency,
                        target_acos, default_budget, default_bid, status, created_at, updated_at
                    """
                ),
                params,
            ).mappings().first()
        return _product_from_row(row) if row else None


_local_repository = LocalProductProfileRepository()


def get_product_profile_repository() -> ProductProfileRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresProductProfileRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def _product_from_row(row: RowMapping) -> ProductProfile:
    return ProductProfile(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_name=row["product_name"],
        asin=row["asin"],
        sku=row["sku"],
        marketplace=row["marketplace"],
        currency=row["currency"],
        target_acos=_decimal(row["target_acos"]),
        default_budget=_decimal(row["default_budget"]),
        default_bid=_decimal(row["default_bid"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _serialize_value(value: object) -> object:
    if hasattr(value, "value"):
        return value.value
    return value


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
