"""Хранение данных PostgreSQL и транзакционные SQL-операции."""

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
    """Заказы, блокировки строк, снимки оплаты и проверки доступа."""

    PAYMENT_TIMEOUT_MINUTES = 15

    def __init__(self, database: Database) -> None:
        """Сохраняет общий пул соединений для операций репозитория.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.database = database

    @staticmethod
    def lock_order(connection: DbConnection, order_id: UUID, legacy_only: bool = False) -> Row:
        """Блокирует родительский заказ перед изменением оплаты или состояния.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param order_id: UUID заказа.
        :param legacy_only: Ограничить обработку заказами прежнего формата.
        :return: Результат операции типа Row.
        """
        row = connection.execute(
            "SELECT * FROM store_orders WHERE id = %s FOR UPDATE", (order_id,)
        ).fetchone()
        if row is None or (legacy_only and row.get("order_kind", "LEGACY") != "LEGACY"):
            raise OrderException(404, "ORDER_NOT_FOUND", "Order was not found")
        return row

    @staticmethod
    def assert_access(order: Row, actor: Row, payments: bool = False, modifying: bool = False) -> None:
        """Проверяет владельца либо ADMIN после блокировки заказа.

        :param order: Строка заказа с текущим состоянием и сохранёнными снимками.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :param payments: История попыток оплаты текущего заказа.
        :param modifying: Выполняет ли операция изменение данных.
        :return: Ничего не возвращает.
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
        """Атомарно меняет доступность питомца и увеличивает его версию.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param pet_id: UUID питомца.
        :param status: Статус ресурса либо HTTP-ответа согласно операции.
        :return: Ничего не возвращает.
        """
        connection.execute(
            "UPDATE pets SET status = %s::pet_status, version = version + 1 WHERE id = %s", (status, pet_id)
        )

    @staticmethod
    def has_active_order(connection: DbConnection, pet_id: UUID) -> bool:
        """Проверяет наличие активного заказа, удерживающего питомца.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param pet_id: UUID питомца.
        :return: True при выполнении проверяемого условия, иначе False.
        """
        return (
            connection.execute(
                """SELECT 1 WHERE EXISTS (SELECT 1 FROM store_orders WHERE pet_id=%s AND status IN ('placed','approved','shipped'))
                   OR EXISTS (SELECT 1 FROM order_lines l JOIN store_orders o ON o.id=l.order_id
                              WHERE l.item_type='pet' AND l.item_id=%s AND o.status IN ('placed','approved','shipped'))""",
                (pet_id, pet_id),
            ).fetchone()
            is not None
        )

    @classmethod
    def expire_locked_order_if_needed(cls, connection: DbConnection, order: Row) -> bool:
        """Просрочивает неоплаченный заказ под существующей блокировкой.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param order: Строка заказа с текущим состоянием и сохранёнными снимками.
        :return: True при выполнении проверяемого условия, иначе False.
        """
        expires = order["payment_expires_at"]
        if order.get("order_kind", "LEGACY") == "MIXED":
            from petstore.service.commerce_order_service import CommerceOrderService

            return CommerceOrderService.expire_locked(connection, order)
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
        """Освобождает просроченные резервы без повторения работы другого worker.

        :return: Числовой результат описанной операции.
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM store_orders WHERE order_kind='LEGACY' AND status = 'placed' AND payment_status = 'UNPAID' AND payment_expires_at <= CURRENT_TIMESTAMP FOR UPDATE SKIP LOCKED"
            ).fetchall()
            return sum(self.expire_locked_order_if_needed(connection, row) for row in rows)

    def get_order_by_id(self, order_id: UUID, actor: Row) -> Row:
        """Возвращает доступный заказ после обработки истёкшего резерва.

        :param order_id: UUID заказа.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Результат операции типа Row.
        """
        self.expire_overdue_orders()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM store_orders WHERE id = %s AND order_kind='LEGACY'", (order_id,)
            ).fetchone()
            if row is None:
                raise OrderException(404, "ORDER_NOT_FOUND", "Order was not found")
            self.assert_access(row, actor)
            return row

    def find_all(self, actor: Row) -> list[Row]:
        """Возвращает все заказы ADMIN или только заказы текущего покупателя.

        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Результат операции типа list[Row].
        """
        self.expire_overdue_orders()
        with self.database.connect() as connection:
            if actor["role"] == "ADMIN":
                return connection.execute(
                    "SELECT * FROM store_orders WHERE order_kind='LEGACY' ORDER BY created_at, id"
                ).fetchall()
            return connection.execute(
                "SELECT * FROM store_orders WHERE owner_user_id = %s AND order_kind='LEGACY' ORDER BY created_at, id",
                (actor["id"],),
            ).fetchall()

    def get_count_by_status(self) -> Row:
        """Возвращает число заказов по состояниям.

        :return: Результат операции типа Row.
        """
        self.expire_overdue_orders()
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT status, COALESCE(SUM(quantity), 0) AS total FROM store_orders WHERE order_kind='LEGACY' GROUP BY status ORDER BY status"
            ).fetchall()
            return {row["status"]: row["total"] for row in rows}

    def create_draft(self, request: OrderCreateRequest, owner: Row) -> Row:
        """Создаёт черновик без резерва и снимков цены или профиля.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :param owner: Идентификатор либо данные владельца ресурса.
        :return: Результат операции типа Row.
        """
        with self.database.connect() as connection:
            UserData.locked_user(connection, owner["id"])
            if (
                connection.execute(
                    "SELECT id FROM pets WHERE id = %s AND publication_status='PUBLISHED' FOR UPDATE",
                    (request.pet_id,),
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
        """Заменяет редактируемые поля черновика в одной транзакции.

        :param order_id: UUID заказа.
        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Результат операции типа Row.
        """
        with self.database.connect() as connection:
            order = self.lock_order(connection, order_id, legacy_only=True)
            self.expire_locked_order_if_needed(connection, order)
            self.assert_access(order, actor, modifying=True)
            if order["status"] != "draft":
                raise OrderException(409, "INVALID_STATUS_TRANSITION", "Only a draft order can be updated")
            if (
                connection.execute(
                    "SELECT id FROM pets WHERE id = %s AND publication_status='PUBLISHED' FOR UPDATE",
                    (request.pet_id,),
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
        """Создаёт снимки оформления и резервирует доступного питомца на 15 минут.

        :param order_id: UUID заказа.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Результат операции типа Row.
        """
        with self.database.connect() as connection:
            order = self.lock_order(connection, order_id, legacy_only=True)
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
            if (
                pet["publication_status"] != "PUBLISHED"
                or pet["status"] != "available"
                or self.has_active_order(connection, order["pet_id"])
            ):
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
        """Атомарно удаляет допустимый заказ и попытки оплаты с сохранением ограничений связей.

        :param order_id: UUID заказа.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Ничего не возвращает.
        """
        with self.database.connect() as connection:
            order = self.lock_order(connection, order_id, legacy_only=True)
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
        """Меняет состояние, выполняет возврат и обновляет питомца в одной транзакции.

        :param order_id: UUID заказа.
        :param target: Целевое состояние жизненного цикла.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Результат операции типа Row.
        """
        with self.database.connect() as connection:
            order = self.lock_order(connection, order_id, legacy_only=True)
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
