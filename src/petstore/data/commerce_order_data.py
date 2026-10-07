"""Mixed-order SQL repository. Callers own the transaction and business decisions."""

import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from petstore.data.database import DbConnection, Row
from petstore.model.enums import OrderStatus
from petstore.utils.responses import Responses


class CommerceOrderData:
    """Persistence only: methods never open/commit a second connection or decide transitions."""

    @staticmethod
    def lines(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Read snapshot lines in stable display order."""
        return connection.execute(
            "SELECT * FROM order_lines WHERE order_id=%s ORDER BY position", (identifier,)
        )

    @staticmethod
    def legacy_pet(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Read a preserved single-pet order's current display name."""
        return connection.execute("SELECT name FROM pets WHERE id=%s", (identifier,))

    @staticmethod
    def history(connection: DbConnection, actor: Row) -> Cursor[Row]:
        """Read the authorized account's order candidates."""
        return connection.execute(
            "SELECT * FROM store_orders WHERE (%s = 'ADMIN' OR owner_user_id=%s) ORDER BY created_at DESC,id",
            (actor["role"], actor["id"]),
        )

    @staticmethod
    def cart_lines(connection: DbConnection, user_id: UUID) -> Cursor[Row]:
        """Read cart quotes under the caller's existing cart lock."""
        return connection.execute(
            "SELECT * FROM cart_lines WHERE user_id=%s ORDER BY item_type,item_id", (user_id,)
        )

    @staticmethod
    def create_draft(connection: DbConnection, user_id: UUID, cart_version: int) -> Cursor[Row]:
        """Insert an unreserved MIXED draft parent."""
        return connection.execute(
            """INSERT INTO store_orders (owner_user_id,pet_id,quantity,status,order_kind,payment_status,cart_version)
               VALUES (%s,NULL,1,'draft','MIXED','NOT_STARTED',%s) RETURNING *""",
            (user_id, cart_version),
        )

    @staticmethod
    def lock_cover(connection: DbConnection, media_id: UUID) -> Cursor[Row]:
        """Protect an immutable order cover after inventory locks."""
        return connection.execute("SELECT id FROM media WHERE id=%s AND NOT deleted FOR UPDATE", (media_id,))

    @staticmethod
    def add_line(
        connection: DbConnection,
        order_id: UUID,
        position: int,
        kind: str,
        item_id: UUID,
        quantity: int,
        name: str,
        sku: str,
        price: Decimal,
        cover_id: UUID | None,
        snapshot: Row,
    ) -> Cursor[Row]:
        """Persist one immutable order line and sanitized cover snapshot."""
        return connection.execute(
            """INSERT INTO order_lines (order_id,position,item_type,item_id,quantity,name,sku,unit_price,cover_id,snapshot)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                order_id,
                position,
                kind,
                item_id,
                quantity,
                name,
                sku,
                price,
                cover_id,
                Jsonb(json.loads(bytes(Responses(snapshot).body))),
            ),
        )

    @staticmethod
    def reserve_product(connection: DbConnection, identifier: UUID, quantity: int) -> Cursor[Row]:
        """Increment reserved inventory; availability is checked by the service."""
        return connection.execute(
            "UPDATE products SET reserved=reserved+%s,version=version+1 WHERE id=%s",
            (quantity, identifier),
        )

    @staticmethod
    def reserve_line(connection: DbConnection, identifier: UUID, position: int) -> Cursor[Row]:
        """Record a line's allocation while its parent is locked."""
        return connection.execute(
            "UPDATE order_lines SET allocation='RESERVED' WHERE order_id=%s AND position=%s",
            (identifier, position),
        )

    @staticmethod
    def place(connection: DbConnection, identifier: UUID, total: Decimal, delivery: Row) -> Cursor[Row]:
        """Persist verified delivery/total and the 15-minute reservation deadline."""
        return connection.execute(
            """UPDATE store_orders SET status='placed',payment_status='UNPAID',total_amount=%s,delivery_details=%s,
               payment_expires_at=CURRENT_TIMESTAMP+INTERVAL '15 minutes',version=version+1 WHERE id=%s RETURNING *""",
            (total, Jsonb(delivery), identifier),
        )

    @staticmethod
    def lock_pet(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Join the shared legacy pet lock ordering."""
        return connection.execute("SELECT id FROM pets WHERE id=%s FOR UPDATE", (identifier,))

    @staticmethod
    def release_product(
        connection: DbConnection, identifier: UUID, quantity: int, consumed: int
    ) -> Cursor[Row]:
        """Apply a guarded reserve/stock decrement exactly once."""
        return connection.execute(
            "UPDATE products SET stock=stock-%s,reserved=reserved-%s,version=version+1 WHERE id=%s AND reserved >= %s",
            (consumed, quantity, identifier, quantity),
        )

    @staticmethod
    def release_line(
        connection: DbConnection, identifier: UUID, position: int, allocation: str
    ) -> Cursor[Row]:
        """Record release/consumption only for a currently RESERVED line."""
        return connection.execute(
            "UPDATE order_lines SET allocation=%s WHERE order_id=%s AND position=%s AND allocation='RESERVED'",
            (allocation, identifier, position),
        )

    @staticmethod
    def restore_product(connection: DbConnection, identifier: UUID, quantity: int) -> Cursor[Row]:
        """Restore a service-approved paid quantity; the locked allocation prevents duplicate refunds."""
        return connection.execute(
            "UPDATE products SET stock=stock+%s,version=version+1 WHERE id=%s", (quantity, identifier)
        )

    @staticmethod
    def restore_line(connection: DbConnection, identifier: UUID, position: int) -> Cursor[Row]:
        """Mark a consumed product allocation restored under its parent lock."""
        return connection.execute(
            "UPDATE order_lines SET allocation='RELEASED' WHERE order_id=%s AND position=%s AND allocation='CONSUMED'",
            (identifier, position),
        )

    @staticmethod
    def set_expired(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Persist a service-approved unpaid expiry."""
        return connection.execute(
            "UPDATE store_orders SET status='expired',payment_status='EXPIRED',complete=TRUE,version=version+1 WHERE id=%s",
            (identifier,),
        )

    @staticmethod
    def overdue(connection: DbConnection) -> Cursor[Row]:
        """Select overdue MIXED parents without waiting for concurrent payments."""
        return connection.execute(
            """SELECT * FROM store_orders WHERE order_kind='MIXED' AND status='placed' AND payment_status='UNPAID'
               AND payment_expires_at<=CURRENT_TIMESTAMP ORDER BY id FOR UPDATE SKIP LOCKED"""
        )

    @staticmethod
    def refund(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Change successful attempts to REFUNDED under the order lock."""
        return connection.execute(
            "UPDATE payments SET status='REFUNDED',updated_at=CURRENT_TIMESTAMP WHERE order_id=%s AND status='SUCCEEDED'",
            (identifier,),
        )

    @staticmethod
    def transition(
        connection: DbConnection,
        identifier: UUID,
        target: OrderStatus,
        payment_status: str,
        ship_date: datetime | None,
    ) -> Cursor[Row]:
        """Persist an already validated lifecycle decision."""
        return connection.execute(
            "UPDATE store_orders SET status=%s::order_status,payment_status=%s::order_payment_status,complete=%s,ship_date=%s,version=version+1 WHERE id=%s RETURNING *",
            (
                target.value,
                payment_status,
                target.is_complete,
                ship_date,
                identifier,
            ),
        )

    @staticmethod
    def delete_payments(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Delete dependent attempts before the RESTRICT-protected parent."""
        return connection.execute("DELETE FROM payments WHERE order_id=%s", (identifier,))

    @staticmethod
    def delete_lines(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Delete immutable lines for a service-approved deletable order."""
        return connection.execute("DELETE FROM order_lines WHERE order_id=%s", (identifier,))

    @staticmethod
    def delete_parent(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Delete a locked parent after its dependent rows."""
        return connection.execute("DELETE FROM store_orders WHERE id=%s", (identifier,))
