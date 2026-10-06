"""Transactional draft, reservation, delivery and refund lifecycle."""

from datetime import UTC, datetime
from uuid import UUID

from psycopg.types.json import Jsonb

from petstore.data.database import Database, DbConnection, Row
from petstore.data.user_data import UserData
from petstore.model.enums import OrderStatus
from petstore.model.requests import OrderCreateRequest
from petstore.service.exceptions import OrderException
from petstore.service.validation_service import ValidationService
from petstore.utils.responses import public_user


class OrderData:
    """Order repository retaining row locks, payment snapshots and ownership rules."""

    PAYMENT_TIMEOUT_MINUTES = 15

    def __init__(self, database: Database) -> None:
        """Use the shared pool without opening an independent transaction.

        :param database: PostgreSQL connection factory.
        """
        self.database = database

    @staticmethod
    def lock_order(connection: DbConnection, order_id: UUID) -> Row:
        """Lock the parent order before any payment or lifecycle mutation.

        :param connection: Existing transaction.
        :param order_id: Parent order UUID.
        """
        row = connection.execute(
            "SELECT * FROM store_orders WHERE id = %s FOR UPDATE", (order_id,)
        ).fetchone()
        if row is None:
            raise OrderException(404, "ORDER_NOT_FOUND", "Order was not found")
        return row

    @staticmethod
    def assert_access(order: Row, actor: Row, payments: bool = False, modifying: bool = False) -> None:
        """Authorize an owner or administrator after acquiring the parent row.

        :param order: Persisted order row.
        :param actor: Authorized user row.
        :param payments: Whether the operation concerns payment history.
        :param modifying: Whether to use the original modification-specific message.
        """
        if actor["role"] != "ADMIN" and actor["id"] != order["owner_user_id"]:
            message = (
                "Users may access only payments for their own orders"
                if payments
                else "Users may modify only their own orders"
                if modifying
                else "Users may access only their own orders"
            )
            raise OrderException(403, "ORDER_ACCESS_DENIED", message)

    @staticmethod
    def update_pet_status(connection: DbConnection, pet_id: UUID, status: str) -> None:
        """Change availability and increment the optimistic pet version atomically.

        :param connection: Current transaction.
        :param pet_id: Reserved pet UUID.
        :param status: New catalog availability.
        """
        connection.execute(
            "UPDATE pets SET status = %s::pet_status, version = version + 1 WHERE id = %s", (status, pet_id)
        )

    @staticmethod
    def has_active_order(connection: DbConnection, pet_id: UUID) -> bool:
        """Check whether a pet is still reserved by an active order.

        :param connection: Current transaction.
        :param pet_id: Catalog UUID.
        """
        return (
            connection.execute(
                "SELECT 1 FROM store_orders WHERE pet_id = %s AND status IN ('placed', 'approved', 'shipped') LIMIT 1",
                (pet_id,),
            ).fetchone()
            is not None
        )

    @classmethod
    def expire_locked_order_if_needed(cls, connection: DbConnection, order: Row) -> bool:
        """Expire a due unpaid order under its existing row lock.

        :param connection: Current transaction.
        :param order: Locked mutable order row.
        """
        expires = order["payment_expires_at"]
        if (
            order["status"] == "placed"
            and order["payment_status"] == "UNPAID"
            and expires is not None
            and expires <= datetime.now(UTC)
        ):
            connection.execute(
                "UPDATE store_orders SET status = 'expired', complete = TRUE, payment_status = 'EXPIRED' WHERE id = %s",
                (order["id"],),
            )
            cls.update_pet_status(connection, order["pet_id"], "available")
            order.update(status="expired", complete=True, payment_status="EXPIRED")
            return True
        return False

    def expire_overdue_orders(self) -> int:
        """Release overdue reservations without duplicating work done by another worker."""
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM store_orders WHERE status = 'placed' AND payment_status = 'UNPAID' AND payment_expires_at <= CURRENT_TIMESTAMP FOR UPDATE SKIP LOCKED"
            ).fetchall()
            return sum(self.expire_locked_order_if_needed(connection, row) for row in rows)

    def get_order_by_id(self, order_id: UUID, actor: Row) -> Row:
        """Read an authorized order after reconciling expired reservations.

        :param order_id: Order UUID.
        :param actor: Authorized user.
        """
        self.expire_overdue_orders()
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM store_orders WHERE id = %s", (order_id,)).fetchone()
            if row is None:
                raise OrderException(404, "ORDER_NOT_FOUND", "Order was not found")
            self.assert_access(row, actor)
            return row

    def find_all(self, actor: Row) -> list[Row]:
        """List all orders for admins or only the caller's orders for users.

        :param actor: Authorized account.
        """
        self.expire_overdue_orders()
        with self.database.connect() as connection:
            if actor["role"] == "ADMIN":
                return connection.execute("SELECT * FROM store_orders ORDER BY created_at, id").fetchall()
            return connection.execute(
                "SELECT * FROM store_orders WHERE owner_user_id = %s ORDER BY created_at, id", (actor["id"],)
            ).fetchall()

    def get_count_by_status(self) -> Row:
        """Return the original inventory totals grouped by order status."""
        self.expire_overdue_orders()
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT status, COALESCE(SUM(quantity), 0) AS total FROM store_orders GROUP BY status ORDER BY status"
            ).fetchall()
            return {row["status"]: row["total"] for row in rows}

    def create_draft(self, request: OrderCreateRequest, owner: Row) -> Row:
        """Create a draft without reserving availability or capturing price/profile snapshots.

        :param request: Validated draft fields.
        :param owner: Authorized order owner.
        """
        with self.database.connect() as connection:
            UserData.locked_user(connection, owner["id"])
            if (
                connection.execute(
                    "SELECT id FROM pets WHERE id = %s FOR UPDATE", (request.pet_id,)
                ).fetchone()
                is None
            ):
                raise OrderException(404, "PET_NOT_FOUND", "Pet was not found")
            row = connection.execute(
                """INSERT INTO store_orders (pet_id, quantity, ship_date, status, complete, owner_user_id,
                   created_at, unit_price, total_amount, currency, delivery_details, payment_status, payment_expires_at)
                   VALUES (%s, %s, NULL, 'draft', FALSE, %s, CURRENT_TIMESTAMP, NULL, NULL, 'RUB', NULL,
                   'NOT_STARTED', NULL) RETURNING *""",
                (request.pet_id, request.quantity, owner["id"]),
            ).fetchone()
            assert row is not None
            return row

    def update_draft(self, order_id: UUID, request: OrderCreateRequest, actor: Row) -> Row:
        """Replace only editable draft fields in one transaction.

        :param order_id: Draft UUID.
        :param request: Replacement pet and quantity.
        :param actor: Owner or administrator.
        """
        with self.database.connect() as connection:
            order = self.lock_order(connection, order_id)
            self.expire_locked_order_if_needed(connection, order)
            self.assert_access(order, actor, modifying=True)
            if order["status"] != "draft":
                raise OrderException(409, "INVALID_STATUS_TRANSITION", "Only a draft order can be updated")
            if (
                connection.execute(
                    "SELECT id FROM pets WHERE id = %s FOR UPDATE", (request.pet_id,)
                ).fetchone()
                is None
            ):
                raise OrderException(404, "PET_NOT_FOUND", "Pet was not found")
            row = connection.execute(
                "UPDATE store_orders SET pet_id = %s, quantity = %s WHERE id = %s RETURNING *",
                (request.pet_id, request.quantity, order_id),
            ).fetchone()
            assert row is not None
            return row

    def place_draft(self, order_id: UUID, actor: Row) -> Row:
        """Capture checkout snapshots and reserve an available pet for fifteen minutes.

        :param order_id: Draft UUID.
        :param actor: Owner or administrator.
        """
        with self.database.connect() as connection:
            order = self.lock_order(connection, order_id)
            self.assert_access(order, actor, modifying=True)
            if order["status"] != "draft":
                raise OrderException(
                    409,
                    "INVALID_STATUS_TRANSITION",
                    f"Order cannot transition from {order['status']} to placed",
                )
            owner = UserData.locked_user(connection, order["owner_user_id"])
            missing = ValidationService.missing_order_profile_fields(owner)
            if missing:
                raise OrderException(
                    409,
                    "PROFILE_INCOMPLETE",
                    "Complete the delivery profile before placing an order",
                    missing,
                )
            expired = connection.execute(
                "SELECT * FROM store_orders WHERE pet_id = %s AND status = 'placed' AND payment_status = 'UNPAID' AND payment_expires_at <= CURRENT_TIMESTAMP FOR UPDATE",
                (order["pet_id"],),
            ).fetchall()
            for old in expired:
                self.expire_locked_order_if_needed(connection, old)
            pet = connection.execute(
                "SELECT * FROM pets WHERE id = %s FOR UPDATE", (order["pet_id"],)
            ).fetchone()
            if pet is None:
                raise OrderException(404, "PET_NOT_FOUND", "Pet was not found")
            if pet["status"] != "available" or self.has_active_order(connection, order["pet_id"]):
                raise OrderException(409, "PET_NOT_AVAILABLE", "Pet is not available for ordering")
            profile = public_user(owner)
            delivery = {field: profile[field] for field in ("firstName", "lastName", "phone", "address")}
            row = connection.execute(
                """UPDATE store_orders SET status = 'placed', unit_price = %s, total_amount = %s,
                   delivery_details = %s, payment_status = 'UNPAID',
                   payment_expires_at = CURRENT_TIMESTAMP + INTERVAL '15 minutes'
                   WHERE id = %s AND status = 'draft' RETURNING *""",
                (pet["price"], pet["price"] * order["quantity"], Jsonb(delivery), order_id),
            ).fetchone()
            assert row is not None
            self.update_pet_status(connection, order["pet_id"], "reserved")
            return row

    def delete_order(self, order_id: UUID, actor: Row) -> None:
        """Delete an allowed order and its attempts atomically, retaining RESTRICT constraints.

        :param order_id: Draft or terminal order UUID.
        :param actor: Owner of a draft, or administrator.
        """
        with self.database.connect() as connection:
            order = self.lock_order(connection, order_id)
            self.expire_locked_order_if_needed(connection, order)
            self.assert_access(order, actor, modifying=True)
            status = OrderStatus(order["status"])
            if status.is_active:
                raise OrderException(409, "ORDER_NOT_DELETABLE", "Active orders cannot be deleted")
            if status != OrderStatus.DRAFT and actor["role"] != "ADMIN":
                raise OrderException(
                    403, "ORDER_ACCESS_DENIED", "Only administrators may delete completed orders"
                )
            connection.execute("DELETE FROM payments WHERE order_id = %s", (order_id,))
            connection.execute("DELETE FROM store_orders WHERE id = %s", (order_id,))

    def transition(self, order_id: UUID, target: OrderStatus, actor: Row) -> Row:
        """Apply a valid transition, refund if needed and reconcile the pet in one transaction.

        :param order_id: Order UUID.
        :param target: Requested destination state.
        :param actor: Authorized owner or administrator.
        """
        with self.database.connect() as connection:
            order = self.lock_order(connection, order_id)
            self.expire_locked_order_if_needed(connection, order)
            self.assert_access(order, actor, modifying=True)
            if not OrderStatus(order["status"]).can_transition_to(target):
                raise OrderException(
                    409,
                    "INVALID_STATUS_TRANSITION",
                    f"Order cannot transition from {order['status']} to {target}",
                )
            if target == OrderStatus.APPROVED and order["payment_status"] not in {"PAID", "NOT_REQUIRED"}:
                raise OrderException(409, "ORDER_NOT_PAID", "The order must be paid before approval")
            ship_date = datetime.now(UTC) if target == OrderStatus.SHIPPED else order["ship_date"]
            payment_status = order["payment_status"]
            if target == OrderStatus.CANCELLED and payment_status == "PAID":
                refunded = connection.execute(
                    "UPDATE payments SET status = 'REFUNDED', updated_at = CURRENT_TIMESTAMP WHERE order_id = %s AND status = 'SUCCEEDED'",
                    (order_id,),
                )
                if refunded.rowcount != 1:
                    raise OrderException(
                        409, "PAYMENT_STATE_CONFLICT", "The successful payment could not be refunded"
                    )
                payment_status = "REFUNDED"
            row = connection.execute(
                "UPDATE store_orders SET status = %s::order_status, complete = %s, ship_date = %s, payment_status = %s::order_payment_status WHERE id = %s RETURNING *",
                (target.value, target.is_complete, ship_date, payment_status, order_id),
            ).fetchone()
            assert row is not None
            if target == OrderStatus.CANCELLED and not self.has_active_order(connection, order["pet_id"]):
                self.update_pet_status(connection, order["pet_id"], "available")
            elif target == OrderStatus.DELIVERED:
                self.update_pet_status(connection, order["pet_id"], "sold")
            return row
