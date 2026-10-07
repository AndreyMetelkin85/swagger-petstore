"""Typed inventory boundary used by checkout and cart policies, never exposed as a public DTO."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from petstore.data.database import Row
from petstore.model.commerce import Publication
from petstore.model.enums import PetStatus
from petstore.service.exceptions import ApiException


class InventoryItem(BaseModel):
    """Validated immutable inventory state read while the caller holds its row lock."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: UUID
    kind: Literal["product", "pet"]
    name: str
    sku: str | None = ""
    price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    publication_status: Publication
    stock: int = Field(default=0, ge=0)
    reserved: int = Field(default=0, ge=0)
    status: PetStatus | None = None

    @classmethod
    def from_row(cls, kind: str, row: Row) -> "InventoryItem":
        """Validate driver values once before any monetary or availability decision."""
        return cls.model_validate({**row, "kind": kind})

    def availability_reason(self, quantity: int) -> str | None:
        """Explain cart unavailability without removing a buyer's soft reference."""
        if self.publication_status != Publication.PUBLISHED or self.price is None:
            return "PRODUCT_UNAVAILABLE" if self.kind == "product" else "PET_NOT_AVAILABLE"
        if self.kind == "product" and self.stock - self.reserved < quantity:
            return "INSUFFICIENT_STOCK"
        if self.kind == "pet" and self.status != PetStatus.AVAILABLE:
            return "PET_NOT_AVAILABLE"
        return None

    def checkout_amount(self, quoted_price: Decimal, quantity: int) -> Decimal:
        """Validate a locked item's quote and availability before any reserve is written.

        :raises ApiException: Publication, price or unreserved inventory has changed.
        :return: Exact line amount; calculations never pass through binary floats.
        """
        if self.publication_status != Publication.PUBLISHED or self.price is None:
            raise ApiException(409, "PRODUCT_UNAVAILABLE", "A checkout item is unpublished")
        if self.price != quoted_price:
            raise ApiException(409, "PRICE_CHANGED", "A checkout price changed; refresh the cart")
        if self.kind == "product" and self.stock - self.reserved < quantity:
            raise ApiException(409, "INSUFFICIENT_STOCK", "Not enough unreserved stock")
        if self.kind == "pet" and self.status != PetStatus.AVAILABLE:
            raise ApiException(409, "PET_NOT_AVAILABLE", "Pet is already reserved or unavailable")
        return self.price * quantity
