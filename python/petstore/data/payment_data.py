"""Simulated card payments with persistent idempotency and transactional order locking."""

import hashlib
from uuid import UUID

from petstore.data.database import Database, Row
from petstore.data.order_data import OrderData
from petstore.model.requests import PaymentRequest
from petstore.service.exceptions import PaymentException


class PaymentData:
    """Test-card payment repository; raw card data is never stored or logged."""

    def __init__(self, database: Database) -> None:
        """Use the application's connection pool.

        :param database: PostgreSQL connection factory.
        """
        self.database = database

    @staticmethod
    def request_hash(order_id: UUID, request: PaymentRequest) -> str:
        """Produce the exact Java canonical request hash for existing idempotency records.

        :param order_id: Parent order UUID.
        :param request: Validated payment payload.
        """
        assert request.cardholder_name is not None
        canonical = f"{order_id}|{request.card_number}|{request.expiry_month}|{request.expiry_year}|{request.cvv}|{request.cardholder_name.strip().upper()}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def advisory_key(key: UUID) -> int:
        """Reproduce Java UUID most/least-significant-bit XOR as a signed PostgreSQL bigint.

        :param key: Idempotency UUID.
        """
        value = (key.int >> 64) ^ (key.int & ((1 << 64) - 1))
        return value if value < (1 << 63) else value - (1 << 64)

    @staticmethod
    def throw_if_declined(payment: Row) -> None:
        """Return the original 402 error after a declined attempt has been committed.

        :param payment: Persisted or replayed attempt.
        """
        if payment["status"] == "DECLINED":
            code = payment["failure_code"]
            message = (
                "The test card has insufficient funds"
                if code == "INSUFFICIENT_FUNDS"
                else "The test card payment was declined"
            )
            raise PaymentException(402, code, message)

    def create_payment(
        self, order_id: UUID, key: UUID, request: PaymentRequest, actor: Row
    ) -> tuple[Row, bool]:
        """Serialize idempotency, payment, expiry and deletion on the same parent order lock.

        :param order_id: Parent order UUID.
        :param key: Required idempotency UUID.
        :param request: Validated test-card data.
        :param actor: Owner or administrator.
        """
        request_hash = self.request_hash(order_id, request)
        with self.database.connect() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (self.advisory_key(key),))
            order = OrderData.lock_order(connection, order_id)
            OrderData.assert_access(order, actor, payments=True)
            existing = connection.execute(
                "SELECT * FROM payments WHERE idempotency_key = %s", (key,)
            ).fetchone()
            if existing:
                if existing["order_id"] != order_id or existing["request_hash"] != request_hash:
                    raise PaymentException(
                        409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was already used with another request"
                    )
                connection.commit()
                self.throw_if_declined(existing)
                return existing, True
            OrderData.expire_locked_order_if_needed(connection, order)
            if order["status"] == "expired" or order["payment_status"] == "EXPIRED":
                connection.commit()
                raise PaymentException(
                    410, "ORDER_PAYMENT_EXPIRED", "The payment period for this order has expired"
                )
            if order["payment_status"] in {"PAID", "REFUNDED"}:
                raise PaymentException(
                    409, "ORDER_ALREADY_PAID", "The order already has a successful payment"
                )
            if order["status"] != "placed" or order["payment_status"] == "NOT_REQUIRED":
                raise PaymentException(
                    409, "ORDER_NOT_PAYABLE", "The order cannot be paid in its current state"
                )
            failures = {"4000000000000002": "PAYMENT_DECLINED", "4000000000009995": "INSUFFICIENT_FUNDS"}
            assert request.card_number is not None
            failure = failures.get(request.card_number)
            status = "DECLINED" if failure else "SUCCEEDED"
            payment = connection.execute(
                """INSERT INTO payments (order_id, idempotency_key, request_hash, amount, currency,
                   status, card_brand, card_last4, failure_code)
                   VALUES (%s, %s, %s, %s, 'RUB', %s::payment_attempt_status, %s, %s, %s) RETURNING *""",
                (
                    order_id,
                    key,
                    request_hash,
                    order["total_amount"],
                    status,
                    "VISA" if request.card_number.startswith("4") else "UNKNOWN",
                    request.card_number[-4:],
                    failure,
                ),
            ).fetchone()
            assert payment is not None
            if status == "SUCCEEDED":
                updated = connection.execute(
                    "UPDATE store_orders SET payment_status = 'PAID' WHERE id = %s AND status = 'placed' AND payment_status = 'UNPAID'",
                    (order_id,),
                )
                if updated.rowcount != 1:
                    raise PaymentException(
                        409, "PAYMENT_STATE_CONFLICT", "The order payment state changed concurrently"
                    )
            # A declined attempt is a saved result, not a transaction failure.
            connection.commit()
            self.throw_if_declined(payment)
            return payment, False

    def find_payments(self, order_id: UUID, actor: Row) -> list[Row]:
        """Read payment history after checking parent-order ownership.

        :param order_id: Parent order UUID.
        :param actor: Owner or administrator.
        """
        with self.database.connect() as connection:
            order = OrderData.lock_order(connection, order_id)
            OrderData.assert_access(order, actor, payments=True)
            return connection.execute(
                "SELECT * FROM payments WHERE order_id = %s ORDER BY created_at, id", (order_id,)
            ).fetchall()

    def get_payment(self, order_id: UUID, payment_id: UUID, actor: Row) -> Row:
        """Read a payment belonging to the authorized parent order.

        :param order_id: Parent order UUID.
        :param payment_id: Attempt UUID.
        :param actor: Owner or administrator.
        """
        with self.database.connect() as connection:
            order = OrderData.lock_order(connection, order_id)
            OrderData.assert_access(order, actor, payments=True)
            row = connection.execute(
                "SELECT * FROM payments WHERE order_id = %s AND id = %s", (order_id, payment_id)
            ).fetchone()
            if row is None:
                raise PaymentException(404, "PAYMENT_NOT_FOUND", "Payment was not found")
            return row

    def delete_declined_payment(self, order_id: UUID, payment_id: UUID) -> None:
        """Delete only a declined attempt under the shared parent-order lock.

        :param order_id: Parent order UUID.
        :param payment_id: Attempt UUID.
        """
        with self.database.connect() as connection:
            OrderData.lock_order(connection, order_id)
            row = connection.execute(
                "SELECT * FROM payments WHERE order_id = %s AND id = %s FOR UPDATE", (order_id, payment_id)
            ).fetchone()
            if row is None:
                raise PaymentException(404, "PAYMENT_NOT_FOUND", "Payment was not found")
            if row["status"] != "DECLINED":
                raise PaymentException(
                    409, "PAYMENT_NOT_DELETABLE", "Only declined payment attempts can be deleted separately"
                )
            connection.execute("DELETE FROM payments WHERE order_id = %s AND id = %s", (order_id, payment_id))
