"""Cart persistence under the caller's user/cart lock and transaction."""

from decimal import Decimal
from uuid import UUID

from psycopg import Cursor

from petstore.data.catalog_data import CatalogData
from petstore.data.database import DbConnection, Row
from petstore.data.user_data import UserData


class CartData:
    """SQL-only cart operations; version/replay and availability rules live in CartService."""

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

    @staticmethod
    def lines(connection: DbConnection, user_id: UUID) -> Cursor[Row]:
        """Read quotes in a deterministic item order."""
        return connection.execute(
            "SELECT * FROM cart_lines WHERE user_id=%s ORDER BY item_type,item_id", (user_id,)
        )

    @staticmethod
    def clear(connection: DbConnection, user_id: UUID) -> None:
        """Delete the locked cart's current positions before full replacement."""
        connection.execute("DELETE FROM cart_lines WHERE user_id=%s", (user_id,))

    @staticmethod
    def append_line(
        connection: DbConnection,
        user_id: UUID,
        kind: str,
        identifier: UUID,
        quantity: int,
        name: str,
        price: Decimal | None,
    ) -> None:
        """Insert a service-calculated soft reference and quote."""
        connection.execute(
            "INSERT INTO cart_lines (user_id,item_type,item_id,quantity,name_snapshot,price_snapshot) VALUES (%s,%s,%s,%s,%s,%s)",
            (user_id, kind, identifier, quantity, name, price),
        )

    @staticmethod
    def bump_version(connection: DbConnection, user_id: UUID) -> Cursor[Row]:
        """Persist one successfully validated replacement version."""
        return connection.execute(
            "UPDATE carts SET version=version+1,updated_at=CURRENT_TIMESTAMP WHERE user_id=%s RETURNING *",
            (user_id,),
        )
