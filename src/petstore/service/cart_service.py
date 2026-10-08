"""Бизнес-правила и согласование операций приложения."""

from uuid import UUID

from petstore.data.cart_data import CartData
from petstore.data.catalog_data import CatalogData
from petstore.data.database import Database, DbConnection, Row
from petstore.data.idempotency_data import IdempotencyData
from petstore.model.commerce import CartCommand
from petstore.model.inventory import InventoryItem
from petstore.service.exceptions import ApiException


class CartService:
    """Изменение собственной корзины под блокировкой её строки."""

    def __init__(self, database: Database) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.database = database

    @classmethod
    def public(cls, connection: DbConnection, cart: Row) -> Row:
        """Возвращает актуальные цены, остатки и причину недоступности позиции.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param cart: Серверная корзина с текущей версией.
        :return: Результат операции типа Row.
        """
        lines = CartData.lines(connection, cart["user_id"]).fetchall()
        result: list[Row] = []
        for line in lines:
            kind, identifier = line["item_type"], line["item_id"]
            row = CartData.item(connection, kind, identifier)
            item = InventoryItem.from_row(kind, row) if row is not None else None
            reason = None
            if item is None:
                reason = "PRODUCT_NOT_FOUND" if kind == "product" else "PET_NOT_FOUND"
            else:
                reason = item.availability_reason(line["quantity"])
            published = item is not None and item.publication_status == "PUBLISHED"
            price = item.price if item is not None and published else line["price_snapshot"]
            result.append(
                {
                    "id": identifier,
                    "kind": kind,
                    "quantity": line["quantity"],
                    "name": item.name if item is not None and published else line["name_snapshot"],
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
        """Возвращает либо создаёт корзину только авторизованного пользователя.

        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Результат операции типа Row.
        """
        with self.database.connect() as connection:
            return self.public(connection, CartData.lock(connection, actor["id"]))

    def replace(self, command: CartCommand, actor: Row, key: UUID | None) -> Row:
        """Атомарно заменяет корзину по версии; повтор объединения гостевой корзины не создаёт дубликаты.

        :param command: Проверенная команда изменения, подготовленная вызывающим слоем.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :param key: Ключ повторного запроса либо идентификатор операции.
        :return: Результат операции типа Row.
        """
        payload = command.model_dump()
        with self.database.connect() as connection:
            replay = IdempotencyData.replay(connection, actor["id"], "cart:replace", key, payload)
            if replay:
                return replay[0]
            cart = CartData.lock(connection, actor["id"])
            if command.version != cart["version"]:
                raise ApiException(409, "CART_VERSION_CONFLICT", "Cart changed; reload it before merging")
            old = {
                (r["item_type"], r["item_id"]): r for r in CartData.lines(connection, actor["id"]).fetchall()
            }
            CartData.clear(connection, actor["id"])
            for line in command.lines:
                row = CartData.item(connection, line.kind, line.id)
                item = InventoryItem.from_row(line.kind, row) if row is not None else None
                previous = old.get((line.kind, line.id), {})
                visible = item is not None and item.publication_status == "PUBLISHED"
                name = (
                    item.name
                    if item is not None and visible
                    else previous.get("name_snapshot", "Unavailable item")
                )
                price = item.price if item is not None and visible else previous.get("price_snapshot")
                CartData.append_line(connection, actor["id"], line.kind, line.id, line.quantity, name, price)
            updated = CartData.bump_version(connection, actor["id"]).fetchone()
            assert updated is not None
            result = self.public(connection, updated)
            IdempotencyData.save(connection, actor["id"], "cart:replace", key, payload, result, 200)
            return result
