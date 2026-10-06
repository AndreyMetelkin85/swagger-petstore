"""Versioned mixed carts with server prices and retained unavailable identities."""

from uuid import UUID

from petstore.data.catalog_data import CatalogData
from petstore.data.database import Database, DbConnection, Row
from petstore.data.idempotency_data import IdempotencyData
from petstore.data.user_data import UserData
from petstore.model.commerce import CartCommand
from petstore.service.exceptions import ApiException


class CartData:
    """A user's cart is mutated only under its own row lock."""

    def __init__(self, database: Database) -> None:
        """Use the shared transaction factory."""
        self.database = database

    @staticmethod
    def lock(connection: DbConnection, user_id: UUID) -> Row:
        """Serialize deletion, cart edits and checkout on a known user/cart."""
        UserData.locked_user(connection, user_id)
        connection.execute("INSERT INTO carts (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        row = connection.execute("SELECT * FROM carts WHERE user_id=%s FOR UPDATE", (user_id,)).fetchone()
        assert row is not None
        return row

    @staticmethod
    def item(connection: DbConnection, kind: str, identifier: UUID) -> Row | None:
        """Read a soft reference without discarding missing/unpublished cart lines."""
        return connection.execute(
            f"SELECT * FROM {CatalogData.table(kind)} WHERE id=%s", (identifier,)
        ).fetchone()

    @classmethod
    def public(cls, connection: DbConnection, cart: Row) -> Row:
        """Return current prices, stock and an explicit unavailability reason."""
        lines = connection.execute(
            "SELECT * FROM cart_lines WHERE user_id=%s ORDER BY item_type,item_id", (cart["user_id"],)
        ).fetchall()
        result: list[Row] = []
        for line in lines:
            kind, identifier = line["item_type"], line["item_id"]
            item = cls.item(connection, kind, identifier)
            reason = None
            if item is None:
                reason = "PRODUCT_NOT_FOUND" if kind == "product" else "PET_NOT_FOUND"
            elif item["publication_status"] != "PUBLISHED":
                reason = "PRODUCT_UNAVAILABLE" if kind == "product" else "PET_NOT_AVAILABLE"
            elif kind == "product" and item["stock"] - item["reserved"] < line["quantity"]:
                reason = "INSUFFICIENT_STOCK"
            elif kind == "pet" and item["status"] != "available":
                reason = "PET_NOT_AVAILABLE"
            published = item is not None and item["publication_status"] == "PUBLISHED"
            price = item["price"] if item is not None and published else line["price_snapshot"]
            result.append(
                {
                    "id": identifier,
                    "kind": kind,
                    "quantity": line["quantity"],
                    "name": item["name"] if item is not None and published else line["name_snapshot"],
                    "price": price,
                    "quotedPrice": line["price_snapshot"],
                    "currency": "RUB",
                    "priceChanged": published and price != line["price_snapshot"],
                    "available": reason is None,
                    "reason": reason,
                    "images": CatalogData.gallery(connection, kind, identifier) if published else [],
                }
            )
        return {"lines": result, "version": cart["version"]}

    def get(self, actor: Row) -> Row:
        """Return or initialize only the authenticated user's cart."""
        with self.database.connect() as connection:
            return self.public(connection, self.lock(connection, actor["id"]))

    def replace(self, command: CartCommand, actor: Row, key: UUID | None) -> Row:
        """Atomically replace a versioned cart; idempotent guest retries cannot duplicate it."""
        payload = command.model_dump()
        with self.database.connect() as connection:
            replay = IdempotencyData.replay(connection, actor["id"], "cart:replace", key, payload)
            if replay:
                return replay[0]
            cart = self.lock(connection, actor["id"])
            if command.version != cart["version"]:
                raise ApiException(409, "CART_VERSION_CONFLICT", "Cart changed; reload it before merging")
            old = {
                (r["item_type"], r["item_id"]): r
                for r in connection.execute(
                    "SELECT * FROM cart_lines WHERE user_id=%s", (actor["id"],)
                ).fetchall()
            }
            connection.execute("DELETE FROM cart_lines WHERE user_id=%s", (actor["id"],))
            for line in command.lines:
                item = self.item(connection, line.kind, line.id)
                previous = old.get((line.kind, line.id), {})
                visible = item is not None and item["publication_status"] == "PUBLISHED"
                name = (
                    item["name"]
                    if item is not None and visible
                    else previous.get("name_snapshot", "Unavailable item")
                )
                price = item["price"] if item is not None and visible else previous.get("price_snapshot")
                connection.execute(
                    "INSERT INTO cart_lines (user_id,item_type,item_id,quantity,name_snapshot,price_snapshot) VALUES (%s,%s,%s,%s,%s,%s)",
                    (actor["id"], line.kind, line.id, line.quantity, name, price),
                )
            updated = connection.execute(
                "UPDATE carts SET version=version+1,updated_at=CURRENT_TIMESTAMP WHERE user_id=%s RETURNING *",
                (actor["id"],),
            ).fetchone()
            assert updated is not None
            result = self.public(connection, updated)
            IdempotencyData.save(connection, actor["id"], "cart:replace", key, payload, result, 200)
            return result
