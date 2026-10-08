"""Бизнес-правила и согласование операций приложения."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from petstore.data.cart_data import CartData
from petstore.data.catalog_data import CatalogData
from petstore.data.commerce_order_data import CommerceOrderData
from petstore.data.database import Database, DbConnection, Row
from petstore.data.idempotency_data import IdempotencyData
from petstore.data.order_data import OrderData
from petstore.data.user_data import UserData
from petstore.model.commerce import CheckoutCommand
from petstore.model.enums import OrderStatus
from petstore.model.inventory import InventoryItem
from petstore.service.catalog_service import CatalogService
from petstore.service.exceptions import ApiException
from petstore.service.validation_service import ValidationService
from petstore.utils.responses import public_delivery, public_user


class CommerceOrderService:
    """Заказ блокируется перед упорядоченными остатками; оплата использует ту же блокировку."""

    def __init__(self, database: Database) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.database = database

    @staticmethod
    def lines(connection: DbConnection, identifier: UUID) -> list[Row]:
        """Возвращает неизменяемые позиции оформления в порядке отображения.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа list[Row].
        """
        return CommerceOrderData.lines(connection, identifier).fetchall()

    @classmethod
    def public(cls, connection: DbConnection, order: Row) -> Row:
        """Формирует общий DTO истории, адаптируя сохранённые заказы с одним питомцем.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param order: Строка заказа с текущим состоянием и сохранёнными снимками.
        :return: Результат операции типа Row.
        """
        lines = cls.lines(connection, order["id"])
        if order["order_kind"] == "LEGACY":
            pet = CommerceOrderData.legacy_pet(connection, order["pet_id"]).fetchone()
            items: list[Row] = [
                {
                    "kind": "pet",
                    "itemId": order["pet_id"],
                    "name": pet["name"] if pet else "Legacy pet",
                    "sku": "",
                    "quantity": order["quantity"],
                    "price": order["unit_price"],
                    "images": [],
                }
            ]
        else:
            items = [
                {
                    "kind": r["item_type"],
                    "itemId": r["item_id"],
                    "name": r["name"],
                    "sku": r["sku"],
                    "quantity": r["quantity"],
                    "price": r["unit_price"],
                    "images": r["snapshot"].get("images", []),
                    "allocation": r["allocation"],
                }
                for r in lines
            ]
        return {
            "id": order["id"],
            "userId": order["owner_user_id"],
            "status": order["status"],
            "paymentStatus": order["payment_status"],
            "version": order["version"],
            "cartVersion": order["cart_version"],
            "createdAt": order["created_at"],
            "shipDate": order["ship_date"],
            "paymentExpiresAt": order["payment_expires_at"],
            "lines": items,
            "total": order["total_amount"],
            "currency": order["currency"],
            "delivery": public_delivery(order["delivery_details"]),
            "complete": order["complete"],
        }

    def get(self, identifier: UUID, actor: Row) -> Row:
        """Возвращает доступный владельцу либо ADMIN заказ после обработки срока резерва.

        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Результат операции типа Row.
        """
        self.expire()
        with self.database.connect() as connection:
            order = OrderData.lock_order(connection, identifier)
            OrderData.assert_access(order, actor)
            return self.public(connection, order)

    def find_all(self, actor: Row) -> list[Row]:
        """Включает сохранённые заказы прежнего формата в общую историю.

        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Результат операции типа list[Row].
        """
        self.expire()
        with self.database.connect() as connection:
            rows = CommerceOrderData.history(connection, actor).fetchall()
            return [self.public(connection, row) for row in rows]

    def create(self, command: CheckoutCommand, actor: Row, key: UUID) -> tuple[Row, bool]:
        """Сохраняет серверные цены корзины в черновике без резервирования остатков.

        :param command: Проверенная команда изменения, подготовленная вызывающим слоем.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :param key: Ключ повторного запроса либо идентификатор операции.
        :return: Результат операции типа tuple[Row, bool].
        """
        payload = command.model_dump()
        with self.database.connect() as connection:
            replay = IdempotencyData.replay(connection, actor["id"], "order:create", key, payload)
            if replay:
                return replay[0], True
            cart = CartData.lock(connection, actor["id"])
            if cart["version"] != command.cart_version:
                raise ApiException(409, "CART_VERSION_CONFLICT", "Cart changed before checkout")
            lines = CommerceOrderData.cart_lines(connection, actor["id"]).fetchall()
            if not lines:
                raise ApiException(422, "CART_EMPTY", "Cart must contain at least one item")
            parent = CommerceOrderData.create_draft(connection, actor["id"], cart["version"]).fetchone()
            assert parent is not None
            inventory = self.inventory_locks(connection, lines)
            galleries = {
                (line["item_type"], line["item_id"]): CatalogData.gallery(
                    connection, line["item_type"], line["item_id"]
                )
                for line in lines
            }
            covers = {
                identity: next((image for image in gallery if image["isCover"]), None)
                for identity, gallery in galleries.items()
            }
            # Остатки блокируются перед упорядоченными изображениями, включая смешанное оформление.
            for media_id in sorted({image["mediaId"] for image in covers.values() if image}, key=str):
                CommerceOrderData.lock_cover(connection, media_id)
            for position, line in enumerate(lines):
                identity = (line["item_type"], line["item_id"])
                item = inventory[identity]
                if item.publication_status != "PUBLISHED":
                    raise ApiException(409, "PRODUCT_UNAVAILABLE", "A cart item is no longer published")
                if item.price is None:
                    raise ApiException(409, "PRODUCT_UNAVAILABLE", "A cart item has no valid price")
                cover = covers[identity]
                price = line["price_snapshot"] if line["price_snapshot"] is not None else item.price
                snapshot = {"images": [cover] if cover else []}
                CommerceOrderData.add_line(
                    connection,
                    parent["id"],
                    position,
                    line["item_type"],
                    line["item_id"],
                    line["quantity"],
                    item.name,
                    item.sku or "",
                    price,
                    cover["mediaId"] if cover else None,
                    snapshot,
                )
            result = self.public(connection, parent)
            IdempotencyData.save(connection, actor["id"], "order:create", key, payload, result, 201)
            return result, False

    @staticmethod
    def inventory_locks(connection: DbConnection, lines: list[Row]) -> dict[tuple[str, UUID], InventoryItem]:
        """Блокирует весь состав в едином порядке для оформления, отмены и истечения резерва.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param lines: Проверенные позиции корзины или заказа.
        :return: Результат операции типа dict[tuple[str, UUID], InventoryItem].
        """
        return {
            (r["item_type"], r["item_id"]): InventoryItem.from_row(
                r["item_type"], CatalogData.locked(connection, r["item_type"], r["item_id"])
            )
            for r in sorted(lines, key=lambda r: (r["item_type"], str(r["item_id"])))
        }

    def place(self, identifier: UUID, actor: Row, version: int, key: UUID) -> Row:
        """Проверяет весь состав до атомарного резервирования любой позиции.

        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :param version: Ожидаемая версия записи для защиты от конкурентного изменения.
        :param key: Ключ повторного запроса либо идентификатор операции.
        :return: Результат операции типа Row.
        """
        self.expire()
        payload: Row = {"orderId": str(identifier), "version": version}
        with self.database.connect() as connection:
            replay = IdempotencyData.replay(connection, actor["id"], "order:place", key, payload)
            if replay:
                return replay[0]
            order = OrderData.lock_order(connection, identifier)
            OrderData.assert_access(order, actor, modifying=True)
            CatalogService.version(order, version, "ORDER_VERSION_CONFLICT")
            if order["order_kind"] != "MIXED" or order["status"] != "draft":
                raise ApiException(409, "INVALID_STATUS_TRANSITION", "Only a mixed draft can be placed")
            cart = CartData.lock(connection, order["owner_user_id"])
            if cart["version"] != order["cart_version"]:
                raise ApiException(
                    409, "CART_VERSION_CONFLICT", "Cart changed after the order draft was created"
                )
            owner = UserData.locked_user(connection, order["owner_user_id"])
            missing = ValidationService.missing_order_profile_fields(owner)
            if missing:
                raise ApiException(
                    409,
                    "PROFILE_INCOMPLETE",
                    "Complete the delivery profile before placing an order",
                    missing,
                )
            phone = re.sub(r"[ ()-]", "", owner["phone"])
            if not re.fullmatch(r"\+7[0-9]{10}", phone):
                raise ApiException(
                    409,
                    "PROFILE_INCOMPLETE",
                    "Complete the delivery profile before placing an order",
                    [{"field": "phone", "message": "Delivery phone must contain +7 and ten digits"}],
                )
            lines = self.lines(connection, identifier)
            inventory = self.inventory_locks(connection, lines)
            total = Decimal("0")
            for line in lines:
                item = inventory[(line["item_type"], line["item_id"])]
                total += item.checkout_amount(line["unit_price"], line["quantity"])
            if total > Decimal("999999999999.99"):
                raise ApiException(422, "VALIDATION_ERROR", "Order total exceeds the monetary limit")
            for line in lines:
                if line["item_type"] == "product":
                    CommerceOrderData.reserve_product(connection, line["item_id"], line["quantity"])
                else:
                    OrderData.update_pet_status(connection, line["item_id"], "reserved")
                CommerceOrderData.reserve_line(connection, identifier, line["position"])
            profile = public_user(owner)
            delivery = {name: profile[name] for name in ("firstName", "lastName", "phone", "address")}
            updated = CommerceOrderData.place(connection, identifier, total, delivery).fetchone()
            assert updated is not None
            CartData.clear(connection, order["owner_user_id"])
            CartData.bump_version(connection, order["owner_user_id"])
            result = self.public(connection, updated)
            IdempotencyData.save(connection, actor["id"], "order:place", key, payload, result, 200)
            return result

    @classmethod
    def release(cls, connection: DbConnection, order: Row, consume: bool = False) -> None:
        """Однократно освобождает или потребляет RESERVED-позиции под блокировкой заказа.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param order: Строка заказа с текущим состоянием и сохранёнными снимками.
        :param consume: Списать резерв вместо простого освобождения.
        :return: Ничего не возвращает.
        """
        if order["order_kind"] == "LEGACY":
            CommerceOrderData.lock_pet(connection, order["pet_id"])
            OrderData.update_pet_status(connection, order["pet_id"], "sold" if consume else "available")
            return
        lines = [
            r
            for r in cls.lines(connection, order["id"])
            if r["allocation"] == "RESERVED"
            or (not consume and r["item_type"] == "product" and r["allocation"] == "CONSUMED")
        ]
        cls.inventory_locks(connection, lines)
        for line in lines:
            if line["item_type"] == "product":
                if line["allocation"] == "CONSUMED":
                    restored = CommerceOrderData.restore_product(
                        connection, line["item_id"], line["quantity"]
                    )
                    if restored.rowcount != 1:
                        raise ApiException(
                            409, "INVENTORY_STATE_CONFLICT", "Paid inventory cannot be restored"
                        )
                    CommerceOrderData.restore_line(connection, order["id"], line["position"])
                    continue
                delta = line["quantity"] if consume else 0
                updated = CommerceOrderData.release_product(
                    connection, line["item_id"], line["quantity"], delta
                )
                if updated.rowcount != 1:
                    raise ApiException(
                        409, "INVENTORY_STATE_CONFLICT", "Reserved inventory cannot be reconciled"
                    )
            else:
                OrderData.update_pet_status(connection, line["item_id"], "sold" if consume else "available")
            CommerceOrderData.release_line(
                connection, order["id"], line["position"], "CONSUMED" if consume else "RELEASED"
            )

    @classmethod
    def consume_paid_products(cls, connection: DbConnection, order: Row) -> None:
        """Однократно списывает товары при успешной оплате; питомцы остаются в резерве до доставки.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param order: Строка заказа с текущим состоянием и сохранёнными снимками.
        :return: Ничего не возвращает.
        """
        if order.get("order_kind", "LEGACY") != "MIXED":
            return
        lines = [
            line
            for line in cls.lines(connection, order["id"])
            if line["item_type"] == "product" and line["allocation"] == "RESERVED"
        ]
        cls.inventory_locks(connection, lines)
        for line in lines:
            updated = CommerceOrderData.release_product(
                connection, line["item_id"], line["quantity"], line["quantity"]
            )
            if updated.rowcount != 1:
                raise ApiException(409, "INVENTORY_STATE_CONFLICT", "Reserved inventory cannot be consumed")
            CommerceOrderData.release_line(connection, order["id"], line["position"], "CONSUMED")

    @classmethod
    def expire_locked(cls, connection: DbConnection, order: Row) -> bool:
        """Обрабатывает истечение неоплаченного заказа под общей блокировкой оплаты и заказа.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param order: Строка заказа с текущим состоянием и сохранёнными снимками.
        :return: True при выполнении проверяемого условия, иначе False.
        """
        if (
            order["status"] != "placed"
            or order["payment_status"] != "UNPAID"
            or order["payment_expires_at"] is None
            or order["payment_expires_at"] > datetime.now(UTC)
        ):
            return False
        cls.release(connection, order)
        CommerceOrderData.set_expired(connection, order["id"])
        order.update(status="expired", payment_status="EXPIRED", complete=True, version=order["version"] + 1)
        return True

    def expire(self) -> int:
        """Просрочивает незаблокированные смешанные заказы; SKIP LOCKED исключает двойное освобождение.

        :return: Числовой результат описанной операции.
        """
        legacy = OrderData(self.database).expire_overdue_orders()
        with self.database.connect() as connection:
            rows = CommerceOrderData.overdue(connection).fetchall()
            return legacy + sum(self.expire_locked(connection, row) for row in rows)

    def transition(self, identifier: UUID, target: OrderStatus, actor: Row, version: int) -> Row:
        """Применяет матрицу состояний и атомарно возвращает успешную оплату.

        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param target: Целевое состояние жизненного цикла.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :param version: Ожидаемая версия записи для защиты от конкурентного изменения.
        :return: Результат операции типа Row.
        """
        with self.database.connect() as connection:
            order = OrderData.lock_order(connection, identifier)
            OrderData.assert_access(order, actor, modifying=True)
            OrderData.expire_locked_order_if_needed(connection, order)
            CatalogService.version(order, version, "ORDER_VERSION_CONFLICT")
            if not OrderStatus(order["status"]).can_transition_to(target):
                raise ApiException(409, "INVALID_STATUS_TRANSITION", "This order transition is not allowed")
            if target == OrderStatus.APPROVED and order["payment_status"] != "PAID":
                raise ApiException(409, "ORDER_NOT_PAID", "Successful payment is required")
            payment_status = order["payment_status"]
            if target == OrderStatus.CANCELLED:
                if payment_status == "PAID":
                    refunded = CommerceOrderData.refund(connection, identifier)
                    if refunded.rowcount != 1:
                        raise ApiException(
                            409, "PAYMENT_STATE_CONFLICT", "Successful payment cannot be refunded"
                        )
                    payment_status = "REFUNDED"
                self.release(connection, order)
            if target == OrderStatus.DELIVERED:
                self.release(connection, order, consume=True)
            row = CommerceOrderData.transition(
                connection,
                identifier,
                target,
                payment_status,
                datetime.now(UTC) if target == OrderStatus.SHIPPED else order["ship_date"],
            ).fetchone()
            assert row is not None
            return self.public(connection, row)

    def delete(self, identifier: UUID, actor: Row) -> None:
        """Удаляет допустимый собственный черновик либо завершённый заказ ADMIN с зависимыми записями.

        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Ничего не возвращает.
        """
        with self.database.connect() as connection:
            order = OrderData.lock_order(connection, identifier)
            OrderData.assert_access(order, actor, modifying=True)
            if order["status"] in {"placed", "approved", "shipped"}:
                raise ApiException(409, "ORDER_NOT_DELETABLE", "Active orders cannot be deleted")
            if order["status"] != "draft" and actor["role"] != "ADMIN":
                raise ApiException(403, "ORDER_ACCESS_DENIED", "Only ADMIN may delete terminal orders")
            CommerceOrderData.delete_payments(connection, identifier)
            CommerceOrderData.delete_lines(connection, identifier)
            CommerceOrderData.delete_parent(connection, identifier)
