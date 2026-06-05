from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductProfileStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


AsinField = Annotated[str | None, Field(default=None, pattern=r"^[A-Z0-9]{10}$")]
PositiveMoney = Annotated[Decimal, Field(gt=Decimal("0"), max_digits=12, decimal_places=4)]
TargetAcos = Annotated[Decimal, Field(gt=Decimal("0"), le=Decimal("1"), max_digits=8, decimal_places=4)]


class ProductProfileBase(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    asin: AsinField = None
    sku: str | None = Field(default=None, max_length=100)
    marketplace: str = Field(default="US", min_length=2, max_length=20)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    target_acos: TargetAcos = Decimal("0.5000")
    default_budget: PositiveMoney = Decimal("10.0000")
    default_bid: PositiveMoney = Decimal("1.0000")
    status: ProductProfileStatus = ProductProfileStatus.ACTIVE
    product_cost: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=12, decimal_places=4)
    product_price: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=12, decimal_places=4)
    margin_pct: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"), max_digits=8, decimal_places=4)
    break_even_acos: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"), max_digits=8, decimal_places=4)
    category: str | None = Field(default=None, max_length=100)
    brand_name: str | None = Field(default=None, max_length=200)

    @field_validator("product_name")
    @classmethod
    def normalize_product_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Product name is required.")
        return normalized

    @field_validator("target_acos")
    @classmethod
    def normalize_percentage(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0001"))

    @field_validator("default_budget", "default_bid", "product_cost", "product_price")
    @classmethod
    def normalize_money(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        return value.quantize(Decimal("0.0001"))

    @field_validator("margin_pct", "break_even_acos")
    @classmethod
    def normalize_margin(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        return value.quantize(Decimal("0.0001"))


class ProductProfileCreate(ProductProfileBase):
    pass


class ProductProfileUpdate(BaseModel):
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    asin: AsinField = None
    sku: str | None = Field(default=None, max_length=100)
    marketplace: str | None = Field(default=None, min_length=2, max_length=20)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    target_acos: TargetAcos | None = None
    default_budget: PositiveMoney | None = None
    default_bid: PositiveMoney | None = None
    status: ProductProfileStatus | None = None
    product_cost: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=12, decimal_places=4)
    product_price: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=12, decimal_places=4)
    margin_pct: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"), max_digits=8, decimal_places=4)
    break_even_acos: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"), max_digits=8, decimal_places=4)
    category: str | None = Field(default=None, max_length=100)
    brand_name: str | None = Field(default=None, max_length=200)

    @field_validator("product_name")
    @classmethod
    def normalize_product_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Product name is required.")
        return normalized

    @field_validator("target_acos")
    @classmethod
    def normalize_percentage(cls, value: Decimal | None) -> Decimal | None:
        return value.quantize(Decimal("0.0001")) if value is not None else value

    @field_validator("default_budget", "default_bid", "product_cost", "product_price")
    @classmethod
    def normalize_money(cls, value: Decimal | None) -> Decimal | None:
        return value.quantize(Decimal("0.0001")) if value is not None else value

    @field_validator("margin_pct", "break_even_acos")
    @classmethod
    def normalize_margin(cls, value: Decimal | None) -> Decimal | None:
        return value.quantize(Decimal("0.0001")) if value is not None else value


class ProductProfile(ProductProfileBase):
    id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BulkDeleteRequest(BaseModel):
    product_ids: list[UUID] = Field(min_length=1, max_length=100)
