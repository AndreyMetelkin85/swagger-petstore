from decimal import Decimal
from uuid import uuid4

import pytest

from petstore.model.inventory import InventoryItem
from petstore.service.exceptions import ApiException


def item(**changes):
    return InventoryItem.model_validate(
        {
            "id": uuid4(),
            "kind": "product",
            "name": "Корм",
            "price": Decimal("10.25"),
            "publication_status": "PUBLISHED",
            "stock": 5,
            "reserved": 2,
            **changes,
        }
    )


def test_quote_calculation_uses_decimal_without_database_access():
    assert item().checkout_amount(Decimal("10.25"), 3) == Decimal("30.75")
    assert item().availability_reason(3) is None


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"publication_status": "DRAFT"}, "PRODUCT_UNAVAILABLE"),
        ({"price": "11.25"}, "PRICE_CHANGED"),
        ({"stock": 2}, "INSUFFICIENT_STOCK"),
        ({"kind": "pet", "status": "reserved"}, "PET_NOT_AVAILABLE"),
    ],
)
def test_checkout_policy_preserves_domain_conflicts(changes, code):
    with pytest.raises(ApiException) as error:
        item(**changes).checkout_amount(Decimal("10.25"), 1)
    assert error.value.status == 409
    assert error.value.code == code


def test_cart_retains_unavailable_pet_with_specific_reason():
    assert (
        item(kind="pet", status="available", publication_status="DRAFT").availability_reason(1)
        == "PET_NOT_AVAILABLE"
    )
    assert item().availability_reason(4) == "INSUFFICIENT_STOCK"
    assert item(kind="pet", status="available").availability_reason(1) is None
    assert item(kind="pet", status="sold").availability_reason(1) == "PET_NOT_AVAILABLE"


def test_repository_boundary_validates_values_and_excludes_private_columns():
    row = {
        "id": uuid4(),
        "name": "Test",
        "price": "0.01",
        "publication_status": "PUBLISHED",
        "stock": 1,
        "reserved": 0,
        "private": "not-public",
    }
    result = InventoryItem.from_row("product", row)
    assert result.price == Decimal("0.01")
    assert "private" not in result.model_dump()
    with pytest.raises(ValueError):
        InventoryItem.from_row("product", {**row, "price": "NaN"})
