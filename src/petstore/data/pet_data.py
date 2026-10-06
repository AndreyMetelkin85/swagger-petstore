"""Pet SQL operations, including optimistic locking and order-history protection."""

import json
from typing import Any, cast
from uuid import UUID, uuid4

from petstore.data.database import Database, Row
from petstore.model.requests import PetCreateRequest, PetUpdateRequest
from petstore.service.exceptions import PetException


class PetData:
    """PostgreSQL-backed catalog with the unchanged nested JSON storage format."""

    def __init__(self, database: Database) -> None:
        """Use the application's connection factory.

        :param database: PostgreSQL pool.
        """
        self.database = database

    @staticmethod
    def public(row: Row) -> Row:
        """Map persisted pet columns to the original response shape.

        :param row: Persisted pet row.
        """
        result = {
            "id": row["id"],
            "name": row["name"],
            "category": json.loads(row["category_json"]),
            "photoUrls": json.loads(row["photo_urls_json"]),
            "tags": json.loads(row["tags_json"]),
            "status": row["status"],
            "price": row["price"],
            "currency": "RUB",
            "version": row["version"],
        }
        return {key: value for key, value in result.items() if value is not None}

    def get_pet_by_id(self, pet_id: UUID) -> Row:
        """Read a public pet or return its operation-specific 404.

        :param pet_id: Catalog UUID.
        """
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM pets WHERE id = %s", (pet_id,)).fetchone()
            if row is None:
                raise PetException(404, "PET_NOT_FOUND", "Pet was not found")
            return self.public(row)

    def find_pet_by_status(self, statuses: str) -> list[Row]:
        """Find pets using the original comma-separated availability filter.

        :param statuses: Validated status list.
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pets WHERE status::text = ANY(%s) ORDER BY id", (statuses.split(","),)
            ).fetchall()
            return [self.public(row) for row in rows]

    def find_pet_by_tags(self, tags: list[str]) -> list[Row]:
        """Return each matching pet once, in original UUID order.

        :param tags: Requested tag names.
        """
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM pets ORDER BY id").fetchall()
            result: list[Row] = []
            for row in rows:
                pet = self.public(row)
                pet_tags = cast(list[Row], pet["tags"] or [])
                if any(tag.get("name") in tags for tag in pet_tags):
                    result.append(pet)
            return result

    @staticmethod
    def nested(request: PetCreateRequest) -> tuple[str, str, str]:
        """Assign missing nested UUIDs and serialize the existing text JSON columns.

        :param request: Validated pet data.
        """
        category: dict[str, Any] | None = None
        if request.category:
            category = {"id": str(request.category.id or uuid4()), "name": request.category.name}
        tags = [{"id": str(tag.id or uuid4()), "name": tag.name} for tag in request.tags or [] if tag]
        return (
            json.dumps(category, ensure_ascii=False),
            json.dumps(request.photo_urls or [], ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False),
        )

    def create_pet(self, request: PetCreateRequest) -> Row:
        """Create a pet with a database-generated UUID and version zero.

        :param request: Validated creation data.
        """
        category, urls, tags = self.nested(request)
        with self.database.connect() as connection:
            row = connection.execute(
                """INSERT INTO pets (category_json, name, photo_urls_json, tags_json, status, price)
                   VALUES (%s, %s, %s, %s, %s::pet_status, %s) RETURNING *""",
                (category, request.name, urls, tags, request.status or "available", request.price),
            ).fetchone()
            assert row is not None
            return self.public(row)

    def update_pet(self, pet_id: UUID, request: PetUpdateRequest) -> Row:
        """Serialize edits and reject stale versions or manual reservation changes.

        :param pet_id: Existing catalog UUID.
        :param request: Validated full update with expected version.
        """
        with self.database.connect() as connection:
            current = connection.execute("SELECT * FROM pets WHERE id = %s FOR UPDATE", (pet_id,)).fetchone()
            if current is None:
                raise PetException(404, "PET_NOT_FOUND", "Pet was not found")
            if request.version != current["version"]:
                raise PetException(
                    409, "PET_VERSION_CONFLICT", "Pet was changed by another request; reload it and retry"
                )
            from petstore.data.order_data import OrderData

            active = OrderData.has_active_order(connection, pet_id)
            if request.status is not None and active:
                raise PetException(409, "PET_HAS_ACTIVE_ORDER", "Pet status is managed by its active order")
            category, urls, tags = self.nested(request)
            row = connection.execute(
                """UPDATE pets SET category_json = %s, name = %s, photo_urls_json = %s, tags_json = %s,
                   status = %s::pet_status, price = %s, version = version + 1
                   WHERE id = %s AND version = %s RETURNING *""",
                (
                    category,
                    request.name,
                    urls,
                    tags,
                    request.status or current["status"],
                    request.price,
                    pet_id,
                    request.version,
                ),
            ).fetchone()
            assert row is not None
            return self.public(row)

    def delete_pet_if_unused(self, pet_id: UUID) -> None:
        """Delete a pet only if no historical or draft order references it.

        :param pet_id: Catalog UUID to delete.
        """
        with self.database.connect() as connection:
            if (
                connection.execute("SELECT id FROM pets WHERE id = %s FOR UPDATE", (pet_id,)).fetchone()
                is None
            ):
                raise PetException(404, "PET_NOT_FOUND", "Pet was not found")
            if connection.execute(
                """SELECT 1 WHERE EXISTS (SELECT 1 FROM store_orders WHERE pet_id=%s)
                   OR EXISTS (SELECT 1 FROM order_lines WHERE item_type='pet' AND item_id=%s)""",
                (pet_id, pet_id),
            ).fetchone():
                raise PetException(409, "PET_HAS_ORDERS", "Pet with order history cannot be deleted")
            connection.execute("DELETE FROM catalog_images WHERE pet_id=%s", (pet_id,))
            connection.execute("DELETE FROM pets WHERE id = %s", (pet_id,))
