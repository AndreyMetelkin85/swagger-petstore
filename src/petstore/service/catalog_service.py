"""Categories, product/pet cards, publication and versioned inventory."""

import json
from typing import Any
from uuid import UUID

from psycopg import errors
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from petstore.data.catalog_data import CatalogData
from petstore.data.database import Database, DbConnection, Row
from petstore.model.commerce import (
    CategoryCommand,
    ImageReference,
    PetCardCommand,
    ProductCommand,
    StockCommand,
)
from petstore.service.exceptions import ApiException


class CatalogService:
    """Coordinate catalog rules and writes using one transaction per command."""

    def __init__(self, database: Database) -> None:
        """Use the application pool without opening independent transactions."""
        self.database = database

    @staticmethod
    def version(row: Row, expected: int | None, code: str = "PRODUCT_VERSION_CONFLICT") -> None:
        """Reject missing/stale optimistic versions before any mutation."""
        if expected is None:
            raise ApiException(
                422,
                "VALIDATION_ERROR",
                "Version is required",
                [{"field": "version", "message": "Version is required"}],
            )
        if row["version"] != expected:
            raise ApiException(409, code, "Reload the current record before updating")

    def categories(self, public: bool, kind: str | None = None) -> list[Row]:
        """List active public categories or all administrator categories."""
        with self.database.connect() as connection:
            rows = CatalogData.categories(connection, public, kind).fetchall()
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "kind": r["kind"],
                    "active": r["active"],
                    "archived": not r["active"],
                    "version": r["version"],
                }
                for r in rows
            ]

    def save_category(self, request: CategoryCommand, identifier: UUID | None = None) -> Row:
        """Create/update a category without deleting associated cards."""
        try:
            with self.database.connect() as connection:
                if identifier is None:
                    row = CatalogData.create_category(
                        connection, request.name.strip(), request.kind, request.active
                    ).fetchone()
                else:
                    current = CatalogData.lock_category(connection, identifier).fetchone()
                    if current is None:
                        raise ApiException(404, "CATEGORY_NOT_FOUND", "Category was not found")
                    self.version(current, request.version, "CATEGORY_VERSION_CONFLICT")
                    if current["kind"] != request.kind:
                        raise ApiException(409, "CATEGORY_KIND_CONFLICT", "Category kind cannot be changed")
                    row = CatalogData.update_category(
                        connection, identifier, request.name.strip(), request.active
                    ).fetchone()
                assert row is not None
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "kind": row["kind"],
                    "active": row["active"],
                    "archived": not row["active"],
                    "version": row["version"],
                }
        except errors.UniqueViolation as exc:
            raise ApiException(409, "CATEGORY_ALREADY_EXISTS", "Category name is already used") from exc

    @staticmethod
    def category(
        connection: DbConnection, identifier: UUID | None, kind: str, required: bool = False
    ) -> None:
        """Validate category kind/activity under a shared row lock."""
        if identifier is None:
            if required:
                raise ApiException(
                    422,
                    "VALIDATION_ERROR",
                    "Category is required",
                    [{"field": "categoryId", "message": "Category is required"}],
                )
            return
        row = CatalogData.share_category(connection, identifier).fetchone()
        if row is None:
            raise ApiException(404, "CATEGORY_NOT_FOUND", "Category was not found")
        if row["kind"] != kind or not row["active"]:
            raise ApiException(
                409, "CATEGORY_UNAVAILABLE", "Category is inactive or belongs to another item kind"
            )

    @staticmethod
    def set_gallery(
        connection: DbConnection, kind: str, identifier: UUID, images: list[ImageReference], name: str
    ) -> None:
        """Lock all referenced media before replacing gallery entries."""
        for media_id in sorted({image.media_id for image in images}, key=str):
            if CatalogData.lock_media(connection, media_id).fetchone() is None:
                raise ApiException(404, "MEDIA_NOT_FOUND", "Gallery media was not found")
        CatalogData.clear_gallery(connection, kind, identifier)
        explicit = any(image.is_cover for image in images)
        for position, image in enumerate(images):
            image = image.model_copy(update={"alt": image.alt or f"{name}, фото {position + 1}"})
            CatalogData.add_gallery_image(
                connection,
                kind,
                identifier,
                position,
                image,
                image.is_cover or (not explicit and position == 0),
            )

    def save(self, request: ProductCommand | PetCardCommand, identifier: UUID | None = None) -> Row:
        """Save a full versioned card; stock/publication remain dedicated operations."""
        kind = "product" if isinstance(request, ProductCommand) else "pet"
        try:
            with self.database.connect() as connection:
                current = CatalogData.locked(connection, kind, identifier) if identifier else None
                if current:
                    self.version(
                        current,
                        request.version,
                        "PRODUCT_VERSION_CONFLICT" if kind == "product" else "PET_VERSION_CONFLICT",
                    )
                published = current is not None and current["publication_status"] == "PUBLISHED"
                if published:
                    self.publication_fields(request, bool(request.images))
                self.category(connection, request.category_id, kind, required=published)
                if isinstance(request, ProductCommand):
                    if current and request.stock is not None and request.stock != current["stock"]:
                        raise ApiException(
                            409, "STOCK_ADJUSTMENT_REQUIRED", "Use a stock adjustment to change inventory"
                        )
                    fields = {
                        "sku": request.sku.strip() if request.sku is not None else None,
                        "name": request.name.strip(),
                        "description": request.description,
                        "category_id": request.category_id,
                        "brand": request.brand,
                        "product_type": request.product_type,
                        "animal_types": Jsonb(request.animal_types),
                        "price": request.price,
                        "feed_form": request.feed_form,
                        "life_stages": Jsonb(request.life_stages),
                        "net_weight_grams": request.net_weight_grams,
                        "ingredients": request.ingredients,
                    }
                    if not current:
                        fields["stock"] = request.stock or 0
                else:
                    fields = {
                        "name": request.name.strip(),
                        "description": request.description,
                        "category_id": request.category_id,
                        "animal_type": request.animal_type,
                        "breed": request.breed,
                        "sex": request.sex,
                        "birth_date": request.birth_date,
                        "price": request.price,
                    }
                    if not current:
                        fields.update(status="available", publication_status="DRAFT")
                if not fields["name"]:
                    raise ApiException(422, "VALIDATION_ERROR", "Name cannot be blank")
                row = (
                    CatalogData.update_card(connection, kind, identifier, fields).fetchone()
                    if identifier is not None
                    else CatalogData.insert_card(connection, kind, fields).fetchone()
                )
                assert row is not None
                self.set_gallery(connection, kind, row["id"], request.images, request.name)
                return CatalogData.public(connection, kind, row)
        except errors.UniqueViolation as exc:
            raise ApiException(
                409,
                "SKU_ALREADY_EXISTS",
                "SKU is already used",
                [{"field": "sku", "message": "SKU is already used"}],
            ) from exc

    def get(self, kind: str, identifier: UUID, public: bool) -> Row:
        """Return an admin card or only a published public card."""
        with self.database.connect() as connection:
            row = CatalogData.get(connection, kind, identifier).fetchone()
            if row is None or (public and row["publication_status"] != "PUBLISHED"):
                raise ApiException(
                    404,
                    "PRODUCT_NOT_FOUND" if kind == "product" else "PET_NOT_FOUND",
                    "Catalog item was not found",
                )
            return CatalogData.public(connection, kind, row)

    def publish(self, kind: str, identifier: UUID, version: int, target: str) -> Row:
        """Versioned publication; availability/stock is not changed."""
        with self.database.connect() as connection:
            row = CatalogData.locked(connection, kind, identifier)
            self.version(
                row, version, "PRODUCT_VERSION_CONFLICT" if kind == "product" else "PET_VERSION_CONFLICT"
            )
            if row["publication_status"] == "ARCHIVED" and target != "ARCHIVED":
                raise ApiException(
                    409, "INVALID_PUBLICATION_TRANSITION", "Archived cards cannot be published"
                )
            if target == "PUBLISHED":
                images = CatalogData.gallery(connection, kind, identifier)
                card = CatalogData.public(connection, kind, row)
                fields = {
                    key: value
                    for key, value in card.items()
                    if key
                    in {
                        "sku",
                        "name",
                        "categoryId",
                        "brand",
                        "productType",
                        "animalTypes",
                        "price",
                        "feedForm",
                        "lifeStages",
                        "netWeightGrams",
                        "animalType",
                    }
                }
                try:
                    command = (
                        ProductCommand.model_validate(fields)
                        if kind == "product"
                        else PetCardCommand.model_validate(fields)
                    )
                except ValidationError as exc:
                    raise ApiException(
                        422,
                        "VALIDATION_ERROR",
                        "Stored card validation failed",
                        [
                            {
                                "field": (".".join(str(part) for part in error["loc"]) or "body")[:100],
                                "message": "Invalid field value",
                            }
                            for error in exc.errors()[:100]
                        ],
                    ) from exc
                self.publication_fields(
                    command, bool(images) or (kind == "pet" and bool(json.loads(row["photo_urls_json"])))
                )
                self.category(connection, row["category_id"], kind, required=True)
            updated = CatalogData.set_publication(connection, kind, identifier, target).fetchone()
            assert updated is not None
            return CatalogData.public(connection, kind, updated)

    @staticmethod
    def publication_fields(request: ProductCommand | PetCardCommand, has_images: bool) -> None:
        """Reject incomplete publication/replacement with field errors, without changing the draft."""
        errors: list[dict[str, str]] = []

        def require(field: str, present: bool) -> None:
            """Append a safe public field error without submitted values."""
            if not present:
                errors.append({"field": field, "message": "Field is required for publication"})

        require("name", bool(request.name.strip()))
        require("categoryId", request.category_id is not None)
        require("price", request.price is not None and request.price > 0)
        if isinstance(request, ProductCommand):
            require("sku", bool(request.sku))
            require("productType", request.product_type is not None)
            require("animalTypes", bool(request.animal_types))
            if request.product_type == "FEED":
                require("brand", bool(request.brand.strip()))
                require("feedForm", bool(request.feed_form))
                require("lifeStages", bool(request.life_stages))
                require("netWeightGrams", request.net_weight_grams is not None)
        else:
            require("animalType", request.animal_type is not None)
        require("images", has_images)
        if errors:
            code = (
                "IMAGE_REQUIRED"
                if len(errors) == 1 and errors[0]["field"] == "images"
                else "PUBLICATION_INCOMPLETE"
            )
            raise ApiException(422, code, "Complete the required fields before publishing", errors)

    def adjust_stock(self, identifier: UUID, command: StockCommand, actor: Row) -> Row:
        """Keep available inventory nonnegative and append an immutable adjustment audit."""
        with self.database.connect() as connection:
            row = CatalogData.locked(connection, "product", identifier)
            self.version(row, command.version)
            value = row["stock"] + command.delta
            if value < row["reserved"] or value > 1000000:
                raise ApiException(409, "INSUFFICIENT_STOCK", "Adjustment cannot remove reserved stock")
            updated = CatalogData.set_stock(connection, identifier, value).fetchone()
            CatalogData.audit_stock(
                connection, identifier, actor["id"], command.delta, command.reason, row["stock"], value
            )
            assert updated is not None
            return CatalogData.public(connection, "product", updated)

    def find_all(self, kind: str, public: bool, query: dict[str, Any]) -> Row:
        """Filter/search/sort with bound values and a bounded page size."""
        try:
            page, size = int(query.get("page", 1)), int(query.get("pageSize", 24))
            if not 1 <= page <= 1000000 or not 1 <= size <= 100:
                raise ValueError
            category = UUID(str(query["categoryId"])) if query.get("categoryId") else None
            minimum = str(query["minPrice"]) if query.get("minPrice") is not None else None
            maximum = str(query["maxPrice"]) if query.get("maxPrice") is not None else None
            from decimal import Decimal

            for price in (minimum, maximum):
                if price is not None and (not Decimal(price).is_finite() or Decimal(price) < 0):
                    raise ValueError
        except (ValueError, ArithmeticError) as exc:
            raise ApiException(422, "VALIDATION_ERROR", "Invalid catalog filters") from exc
        orderings = {
            "name": "name ASC",
            "priceAsc": "price ASC",
            "priceDesc": "price DESC",
            "newest": "created_at DESC" if kind == "product" else "id DESC",
        }
        sort = str(query.get("sort", "name"))
        if sort not in orderings:
            raise ApiException(422, "VALIDATION_ERROR", "Unknown sort order")
        with self.database.connect() as connection:
            count, rows = CatalogData.search(
                connection, kind, public, query, page, size, category, minimum, maximum, orderings[sort]
            )
            assert count is not None
            return {
                "items": [CatalogData.public(connection, kind, row) for row in rows],
                "page": page,
                "pageSize": size,
                "total": count["count"],
            }
