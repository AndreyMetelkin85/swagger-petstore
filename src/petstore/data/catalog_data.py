"""Categories, product/pet cards, publication and versioned inventory."""

import json
from typing import Any, LiteralString, cast
from uuid import UUID

from psycopg import errors, sql
from psycopg.types.json import Jsonb

from petstore.data.database import Database, DbConnection, Row
from petstore.model.commerce import (
    CategoryCommand,
    ImageReference,
    PetCardCommand,
    ProductCommand,
    StockCommand,
)
from petstore.service.exceptions import ApiException


class CatalogData:
    """Catalog repository; inventory locks are shared with checkout transactions."""

    def __init__(self, database: Database) -> None:
        """Use the application pool without opening independent transactions."""
        self.database = database

    @staticmethod
    def table(kind: str) -> LiteralString:
        """Return an allowlisted identifier; user input is never interpolated as SQL."""
        if kind not in {"product", "pet"}:
            raise ApiException(422, "VALIDATION_ERROR", "Unknown item kind")
        return "products" if kind == "product" else "pets"

    @classmethod
    def locked(cls, connection: DbConnection, kind: str, identifier: UUID) -> Row:
        """Acquire a catalog row under the caller's existing transaction."""
        row = connection.execute(
            f"SELECT * FROM {cls.table(kind)} WHERE id = %s FOR UPDATE", (identifier,)
        ).fetchone()
        if row is None:
            raise ApiException(
                404,
                "PRODUCT_NOT_FOUND" if kind == "product" else "PET_NOT_FOUND",
                "Catalog item was not found",
            )
        return row

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

    @staticmethod
    def gallery(connection: DbConnection, kind: str, identifier: UUID) -> list[Row]:
        """Read gallery order/cover without exposing storage paths."""
        column = "product_id" if kind == "product" else "pet_id"
        rows = connection.execute(
            f"SELECT media_id, position, alt, is_cover FROM catalog_images WHERE {column} = %s ORDER BY position",
            (identifier,),
        ).fetchall()
        return [
            {
                "mediaId": row["media_id"],
                "position": row["position"],
                "alt": row["alt"],
                "isCover": row["is_cover"],
                "imageUrl": f"/api/v3/media/{row['media_id']}/image",
                "thumbUrl": f"/api/v3/media/{row['media_id']}/thumb",
            }
            for row in rows
        ]

    @classmethod
    def public(cls, connection: DbConnection, kind: str, row: Row) -> Row:
        """Map database columns to the documented card DTO."""
        common = {
            "id": row["id"],
            "kind": kind,
            "name": row["name"],
            "description": row["description"],
            "categoryId": row["category_id"],
            "price": row["price"],
            "currency": "RUB",
            "publicationStatus": row["publication_status"],
            "version": row["version"],
            "images": cls.gallery(connection, kind, row["id"]),
        }
        if kind == "product":
            common.update(
                sku=row["sku"],
                brand=row["brand"],
                productType=row["product_type"],
                animalTypes=row["animal_types"],
                feedForm=row["feed_form"],
                lifeStages=row["life_stages"],
                netWeightGrams=row["net_weight_grams"],
                ingredients=row["ingredients"],
                stock=row["stock"],
                reserved=row["reserved"],
                availableQuantity=row["stock"] - row["reserved"],
            )
        else:
            common.update(
                animalType=row["animal_type"],
                breed=row["breed"],
                sex=row["sex"],
                birthDate=row["birth_date"].isoformat() if row["birth_date"] else None,
                status=row["status"],
                photoUrls=json.loads(row["photo_urls_json"]),
            )
        return common

    def categories(self, public: bool, kind: str | None = None) -> list[Row]:
        """List active public categories or all administrator categories."""
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM catalog_categories WHERE (%s = FALSE OR active) AND (%s::text IS NULL OR kind = %s) ORDER BY name, id",
                (public, kind, kind),
            ).fetchall()
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
                    row = connection.execute(
                        "INSERT INTO catalog_categories (name,kind,active) VALUES (%s,%s,%s) RETURNING *",
                        (request.name.strip(), request.kind, request.active),
                    ).fetchone()
                else:
                    current = connection.execute(
                        "SELECT * FROM catalog_categories WHERE id=%s FOR UPDATE", (identifier,)
                    ).fetchone()
                    if current is None:
                        raise ApiException(404, "CATEGORY_NOT_FOUND", "Category was not found")
                    self.version(current, request.version, "CATEGORY_VERSION_CONFLICT")
                    if current["kind"] != request.kind:
                        raise ApiException(409, "CATEGORY_KIND_CONFLICT", "Category kind cannot be changed")
                    row = connection.execute(
                        "UPDATE catalog_categories SET name=%s,active=%s,version=version+1 WHERE id=%s RETURNING *",
                        (request.name.strip(), request.active, identifier),
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
        row = connection.execute(
            "SELECT * FROM catalog_categories WHERE id=%s FOR SHARE", (identifier,)
        ).fetchone()
        if row is None:
            raise ApiException(404, "CATEGORY_NOT_FOUND", "Category was not found")
        if row["kind"] != kind or not row["active"]:
            raise ApiException(
                409, "CATEGORY_UNAVAILABLE", "Category is inactive or belongs to another item kind"
            )

    @staticmethod
    def set_gallery(
        connection: DbConnection, kind: str, identifier: UUID, images: list[ImageReference]
    ) -> None:
        """Lock all referenced media before replacing gallery entries."""
        for media_id in sorted({image.media_id for image in images}, key=str):
            if (
                connection.execute(
                    "SELECT id FROM media WHERE id=%s AND NOT deleted FOR UPDATE", (media_id,)
                ).fetchone()
                is None
            ):
                raise ApiException(404, "MEDIA_NOT_FOUND", "Gallery media was not found")
        column = "product_id" if kind == "product" else "pet_id"
        connection.execute(f"DELETE FROM catalog_images WHERE {column}=%s", (identifier,))
        explicit = any(image.is_cover for image in images)
        for position, image in enumerate(images):
            connection.execute(
                f"INSERT INTO catalog_images ({column},media_id,position,alt,is_cover) VALUES (%s,%s,%s,%s,%s)",
                (
                    identifier,
                    image.media_id,
                    position,
                    image.alt,
                    image.is_cover or (not explicit and position == 0),
                ),
            )

    def save(self, request: ProductCommand | PetCardCommand, identifier: UUID | None = None) -> Row:
        """Save a full versioned card; stock/publication remain dedicated operations."""
        kind = "product" if isinstance(request, ProductCommand) else "pet"
        try:
            with self.database.connect() as connection:
                current = self.locked(connection, kind, identifier) if identifier else None
                if current:
                    self.version(
                        current,
                        request.version,
                        "PRODUCT_VERSION_CONFLICT" if kind == "product" else "PET_VERSION_CONFLICT",
                    )
                published = current is not None and current["publication_status"] == "PUBLISHED"
                self.category(connection, request.category_id, kind, required=published and kind == "product")
                if (
                    published
                    and not request.images
                    and not (kind == "pet" and current is not None and json.loads(current["photo_urls_json"]))
                ):
                    raise ApiException(422, "IMAGE_REQUIRED", "Published cards must keep at least one image")
                if isinstance(request, ProductCommand):
                    if current and request.stock is not None and request.stock != current["stock"]:
                        raise ApiException(
                            409, "STOCK_ADJUSTMENT_REQUIRED", "Use a stock adjustment to change inventory"
                        )
                    fields = {
                        "sku": request.sku.strip(),
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
                columns = list(fields)
                if current:
                    assignments = sql.SQL(",").join(
                        sql.SQL("{}=%s").format(sql.Identifier(column)) for column in columns
                    )
                    row = connection.execute(
                        sql.SQL("UPDATE {} SET {},version=version+1 WHERE id=%s RETURNING *").format(
                            sql.Identifier(self.table(kind)), assignments
                        ),
                        (*fields.values(), identifier),
                    ).fetchone()
                else:
                    row = connection.execute(
                        sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
                            sql.Identifier(self.table(kind)),
                            sql.SQL(",").join(sql.Identifier(column) for column in columns),
                            sql.SQL(",").join(sql.Placeholder() for _ in columns),
                        ),
                        tuple(fields.values()),
                    ).fetchone()
                assert row is not None
                self.set_gallery(connection, kind, row["id"], request.images)
                return self.public(connection, kind, row)
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
            row = connection.execute(
                f"SELECT * FROM {self.table(kind)} WHERE id=%s", (identifier,)
            ).fetchone()
            if row is None or (public and row["publication_status"] != "PUBLISHED"):
                raise ApiException(
                    404,
                    "PRODUCT_NOT_FOUND" if kind == "product" else "PET_NOT_FOUND",
                    "Catalog item was not found",
                )
            return self.public(connection, kind, row)

    def publish(self, kind: str, identifier: UUID, version: int, target: str) -> Row:
        """Versioned publication; availability/stock is not changed."""
        with self.database.connect() as connection:
            row = self.locked(connection, kind, identifier)
            self.version(
                row, version, "PRODUCT_VERSION_CONFLICT" if kind == "product" else "PET_VERSION_CONFLICT"
            )
            if row["publication_status"] == "ARCHIVED" and target == "PUBLISHED":
                raise ApiException(
                    409, "INVALID_PUBLICATION_TRANSITION", "Archived cards cannot be published"
                )
            if target == "PUBLISHED":
                self.category(connection, row["category_id"], kind, required=kind == "product")
                images = self.gallery(connection, kind, identifier)
                if not images and not (kind == "pet" and json.loads(row["photo_urls_json"])):
                    raise ApiException(
                        422, "IMAGE_REQUIRED", "At least one image is required for publication"
                    )
            updated = connection.execute(
                f"UPDATE {self.table(kind)} SET publication_status=%s,version=version+1 WHERE id=%s RETURNING *",
                (target, identifier),
            ).fetchone()
            assert updated is not None
            return self.public(connection, kind, updated)

    def adjust_stock(self, identifier: UUID, command: StockCommand, actor: Row) -> Row:
        """Keep available inventory nonnegative and append an immutable adjustment audit."""
        with self.database.connect() as connection:
            row = self.locked(connection, "product", identifier)
            self.version(row, command.version)
            value = row["stock"] + command.delta
            if value < row["reserved"] or value > 1000000:
                raise ApiException(409, "INSUFFICIENT_STOCK", "Adjustment cannot remove reserved stock")
            updated = connection.execute(
                "UPDATE products SET stock=%s,version=version+1 WHERE id=%s RETURNING *", (value, identifier)
            ).fetchone()
            connection.execute(
                "INSERT INTO stock_adjustments (product_id,actor_id,delta,reason,before_stock,after_stock) VALUES (%s,%s,%s,%s,%s,%s)",
                (identifier, actor["id"], command.delta, command.reason, row["stock"], value),
            )
            assert updated is not None
            return self.public(connection, "product", updated)

    def find_all(self, kind: str, public: bool, query: dict[str, Any]) -> Row:
        """Filter/search/sort with bound values and a bounded page size."""
        try:
            page, size = int(query.get("page", 1)), int(query.get("pageSize", 24))
            if page < 1 or not 1 <= size <= 100:
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
        conditions = [
            "(%s = FALSE OR publication_status='PUBLISHED')",
            "(%s::uuid IS NULL OR category_id=%s)",
            "(%s::numeric IS NULL OR price >= %s::numeric)",
            "(%s::numeric IS NULL OR price <= %s::numeric)",
        ]
        values: list[Any] = [public, category, category, minimum, minimum, maximum, maximum]
        term = str(query.get("q", ""))[:150]
        conditions.append("(name ILIKE %s OR description ILIKE %s)")
        values.extend(["%" + term + "%"] * 2)
        for param, column in (
            ("brand", "brand"),
            ("productType", "product_type"),
            ("feedForm", "feed_form"),
            ("publicationStatus", "publication_status"),
            ("status", "status"),
        ):
            if query.get(param) and (
                (kind == "product" and param != "status")
                or (kind == "pet" and param in {"status", "publicationStatus"})
            ):
                conditions.append(f"{column}=%s")
                values.append(str(query[param]))
        if query.get("animalType"):
            if kind == "product":
                conditions.append("animal_types ? %s")
            else:
                conditions.append("animal_type=%s")
            values.append(str(query["animalType"]))
        where = sql.SQL(" AND ").join(sql.SQL(cast(LiteralString, clause)) for clause in conditions)
        with self.database.connect() as connection:
            count = connection.execute(
                sql.SQL("SELECT COUNT(*) AS count FROM {} WHERE {}").format(
                    sql.Identifier(self.table(kind)), where
                ),
                tuple(values),
            ).fetchone()
            rows = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE {} ORDER BY {},id LIMIT %s OFFSET %s").format(
                    sql.Identifier(self.table(kind)), where, sql.SQL(cast(LiteralString, orderings[sort]))
                ),
                (*values, size, (page - 1) * size),
            ).fetchall()
            assert count is not None
            return {
                "items": [self.public(connection, kind, row) for row in rows],
                "page": page,
                "pageSize": size,
                "total": count["count"],
            }
