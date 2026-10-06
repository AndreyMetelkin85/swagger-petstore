"""Validated catalog, gallery, cart and checkout commands."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from petstore.model.requests import RequestModel


class CommerceRequest(RequestModel):
    """Reject unsupported fields rather than accepting client-controlled stock or totals."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Publication(StrEnum):
    """Visibility independent of inventory availability."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class Animal(StrEnum):
    """Supported audience/species filters."""

    DOG = "dog"
    CAT = "cat"
    BIRD = "bird"
    RODENT = "rodent"
    FISH = "fish"
    REPTILE = "reptile"
    OTHER = "other"


class ImageReference(CommerceRequest):
    """Ordered gallery entry; at most one explicit cover per card."""

    media_id: UUID = Field(alias="mediaId")
    alt: str = Field(default="", max_length=300)
    is_cover: bool = Field(default=False, alias="isCover")


class CategoryCommand(CommerceRequest):
    """Category creation or versioned update; deactivation does not delete its cards."""

    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern="^(product|pet)$")
    active: bool = True
    version: int | None = Field(default=None, ge=0)


class ProductCommand(CommerceRequest):
    """Full product card; stock edits use the dedicated adjustment operation."""

    sku: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=5000)
    category_id: UUID | None = Field(default=None, alias="categoryId")
    brand: str = Field(default="", max_length=100)
    product_type: str = Field(
        default="OTHER", alias="productType", pattern="^(FEED|TREAT|TOY|ACCESSORY|HYGIENE|OTHER)$"
    )
    animal_types: list[Animal] = Field(default_factory=list[Animal], alias="animalTypes", max_length=7)
    price: Decimal = Field(ge=0, le=Decimal("9999999999.99"), multiple_of=0.01)
    feed_form: str = Field(default="", alias="feedForm", pattern="^(|DRY|WET)$")
    life_stages: list[str] = Field(default_factory=list, alias="lifeStages", max_length=20)
    net_weight_grams: int | None = Field(default=None, alias="netWeightGrams", ge=1, le=1000000)
    ingredients: str = Field(default="", max_length=5000)
    images: list[ImageReference] = Field(default_factory=list[ImageReference], max_length=20)
    version: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0, le=1000000)

    @model_validator(mode="after")
    def validate_gallery_and_feed(self) -> Self:
        """Require unique gallery IDs, one cover and meaningful feed attributes."""
        validate_gallery(self.images)
        if self.product_type == "FEED" and (
            not self.feed_form or self.net_weight_grams is None or not self.ingredients.strip()
        ):
            raise ValueError("Feed requires form, package weight and ingredients")
        if any(not value.strip() or len(value) > 50 for value in self.life_stages):
            raise ValueError("Invalid life stage")
        return self


class PetCardCommand(CommerceRequest):
    """Extended pet card without client-controlled reservations/publication state."""

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    animal_type: Animal = Field(default=Animal.OTHER, alias="animalType")
    category_id: UUID | None = Field(default=None, alias="categoryId")
    breed: str = Field(default="", max_length=100)
    sex: str = Field(default="UNKNOWN", pattern="^(MALE|FEMALE|UNKNOWN)$")
    birth_date: date | None = Field(default=None, alias="birthDate")
    price: Decimal = Field(ge=0, le=Decimal("9999999999.99"), multiple_of=0.01)
    images: list[ImageReference] = Field(default_factory=list[ImageReference], max_length=20)
    version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_pet(self) -> Self:
        """Reject future birth dates and ambiguous gallery covers."""
        validate_gallery(self.images)
        if self.birth_date is not None and self.birth_date > date.today():
            raise ValueError("Birth date cannot be in the future")
        return self


def validate_gallery(images: list[ImageReference]) -> None:
    """Validate unique IDs and cover selection before acquiring database locks.

    :param images: Ordered gallery references.
    """
    if (
        len({image.media_id for image in images}) != len(images)
        or sum(image.is_cover for image in images) > 1
    ):
        raise ValueError("Gallery must contain unique media IDs and at most one cover")


class VersionCommand(CommerceRequest):
    """Expected optimistic version for publication/lifecycle actions."""

    version: int = Field(ge=0)


class StockCommand(VersionCommand):
    """Audited inventory delta; reserved stock cannot be removed."""

    delta: int = Field(ge=-1000000, le=1000000)
    reason: str = Field(min_length=1, max_length=300)


class CartLineCommand(CommerceRequest):
    """A soft catalog reference that can remain visible when unavailable."""

    kind: str = Field(pattern="^(product|pet)$")
    id: UUID
    quantity: int = Field(ge=1, le=1000000)

    @model_validator(mode="after")
    def validate_quantity(self) -> Self:
        """An individual pet cannot have a quantity other than one."""
        if self.kind == "pet" and self.quantity != 1:
            raise ValueError("Quantity must be 1 for an individual pet")
        return self


class CartCommand(VersionCommand):
    """Versioned full replacement; optional idempotency protects guest merging."""

    lines: list[CartLineCommand] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_lines(self) -> Self:
        """Reject duplicate identities rather than silently double-counting a merge."""
        if len({(line.kind, line.id) for line in self.lines}) != len(self.lines):
            raise ValueError("Cart must contain unique items")
        return self


class CheckoutCommand(CommerceRequest):
    """Snapshot only a known version of the server-side cart."""

    cart_version: int = Field(alias="cartVersion", ge=1)


class TelemetryEvent(CommerceRequest):
    """Allowlisted operational telemetry without arbitrary strings or personal data."""

    event: str = Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")
    method: str | None = Field(default=None, pattern="^(GET|POST|PUT|DELETE|PATCH)$")
    http_status: int | None = Field(default=None, alias="httpStatus", ge=100, le=599)
    duration_ms: int | None = Field(default=None, alias="durationMs", ge=0, le=3600000)


class TelemetryCommand(CommerceRequest):
    """Bounded batch; unknown metadata is rejected instead of logged."""

    events: list[TelemetryEvent] = Field(min_length=1, max_length=100)
