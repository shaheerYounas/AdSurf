from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.api.app.schemas.product_profiles import ProductProfileCreate


def test_product_profile_defaults() -> None:
    profile = ProductProfileCreate(product_name="Vinyl Tool")

    assert profile.marketplace == "US"
    assert profile.currency == "USD"
    assert profile.target_acos == Decimal("0.5000")
    assert profile.default_budget == Decimal("10.0000")
    assert profile.default_bid == Decimal("1.0000")


def test_product_profile_name_is_trimmed() -> None:
    profile = ProductProfileCreate(product_name="  Vinyl Tool  ")

    assert profile.product_name == "Vinyl Tool"


def test_product_profile_rejects_whitespace_only_name() -> None:
    with pytest.raises(ValidationError):
        ProductProfileCreate(product_name="   ")


@pytest.mark.parametrize("field,value", [("target_acos", 0), ("target_acos", 1.1), ("default_budget", 0), ("default_bid", 0)])
def test_product_profile_numeric_validation(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        ProductProfileCreate(product_name="Vinyl Tool", **{field: value})


def test_product_profile_asin_validation() -> None:
    ProductProfileCreate(product_name="Vinyl Tool", asin="B0ABC12345")

    with pytest.raises(ValidationError):
        ProductProfileCreate(product_name="Vinyl Tool", asin="bad-asin")
