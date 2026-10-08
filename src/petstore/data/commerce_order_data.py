"""Хранение данных PostgreSQL и транзакционные SQL-операции."""

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
    """SQL смешанных заказов без самостоятельных транзакций и решений о переходах."""

    @staticmethod
    def lines(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Возвращает снимки позиций заказа в порядке отображения.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "SELECT * FROM order_lines WHERE order_id=%s ORDER BY position", (identifier,)
        )

    @staticmethod
    def legacy_pet(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Читает имя питомца для сохранённого заказа прежнего формата.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute("SELECT name FROM pets WHERE id=%s", (identifier,))

    @staticmethod
    def history(connection: DbConnection, actor: Row) -> Cursor[Row]:
        """Читает заказы, доступные указанному аккаунту.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "SELECT * FROM store_orders WHERE (%s = 'ADMIN' OR owner_user_id=%s) ORDER BY created_at DESC,id",
            (actor["role"], actor["id"]),
        )

    @staticmethod
    def cart_lines(connection: DbConnection, user_id: UUID) -> Cursor[Row]:
        """Читает сохранённые цены корзины под существующей блокировкой.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param user_id: UUID целевого пользователя.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "SELECT * FROM cart_lines WHERE user_id=%s ORDER BY item_type,item_id", (user_id,)
        )

    @staticmethod
    def create_draft(connection: DbConnection, user_id: UUID, cart_version: int) -> Cursor[Row]:
        """Добавляет родительскую запись MIXED-черновика без резерва.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param user_id: UUID целевого пользователя.
        :param cart_version: Ожидаемая версия серверной корзины при оформлении.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            """INSERT INTO store_orders (owner_user_id,pet_id,quantity,status,order_kind,payment_status,cart_version)
               VALUES (%s,NULL,1,'draft','MIXED','NOT_STARTED',%s) RETURNING *""",
            (user_id, cart_version),
        )

    @staticmethod
    def lock_cover(connection: DbConnection, media_id: UUID) -> Cursor[Row]:
        """Блокирует обложку снимка заказа после блокировок остатков.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param media_id: UUID изображения.
        :return: Результат операции типа Cursor[Row].
        """
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
        """Сохраняет неизменяемую позицию заказа и безопасный снимок обложки.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param order_id: UUID заказа.
        :param position: Порядковый номер изображения в галерее.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param item_id: UUID позиции каталога.
        :param quantity: Количество единиц позиции; для питомца всегда одна.
        :param name: Имя поля, параметра или ресурса текущей операции.
        :param sku: Уникальный артикул товара.
        :param price: Цена в рублях с точностью до копейки.
        :param cover_id: UUID выбранной обложки.
        :param snapshot: Сохранённый неизменяемый снимок данных оформления.
        :return: Результат операции типа Cursor[Row].
        """
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
        """Увеличивает резерв товара после проверки доступности сервисом.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param quantity: Количество единиц позиции; для питомца всегда одна.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE products SET reserved=reserved+%s,version=version+1 WHERE id=%s",
            (quantity, identifier),
        )

    @staticmethod
    def reserve_line(connection: DbConnection, identifier: UUID, position: int) -> Cursor[Row]:
        """Отмечает резерв позиции под блокировкой родительского заказа.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param position: Порядковый номер изображения в галерее.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE order_lines SET allocation='RESERVED' WHERE order_id=%s AND position=%s",
            (identifier, position),
        )

    @staticmethod
    def place(connection: DbConnection, identifier: UUID, total: Decimal, delivery: Row) -> Cursor[Row]:
        """Сохраняет проверенную доставку, сумму и срок резерва на 15 минут.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param total: Сумма заказа, рассчитанная сервером.
        :param delivery: Проверенный снимок контактов и адреса доставки.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            """UPDATE store_orders SET status='placed',payment_status='UNPAID',total_amount=%s,delivery_details=%s,
               payment_expires_at=CURRENT_TIMESTAMP+INTERVAL '15 minutes',version=version+1 WHERE id=%s RETURNING *""",
            (total, Jsonb(delivery), identifier),
        )

    @staticmethod
    def lock_pet(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Блокирует питомца в общем порядке блокировок старых и новых заказов.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute("SELECT id FROM pets WHERE id=%s FOR UPDATE", (identifier,))

    @staticmethod
    def release_product(
        connection: DbConnection, identifier: UUID, quantity: int, consumed: int
    ) -> Cursor[Row]:
        """Однократно уменьшает резерв или остаток с проверкой текущего состояния.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param quantity: Количество единиц позиции; для питомца всегда одна.
        :param consumed: Признак уже списанного количества позиции.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE products SET stock=stock-%s,reserved=reserved-%s,version=version+1 WHERE id=%s AND reserved >= %s",
            (consumed, quantity, identifier, quantity),
        )

    @staticmethod
    def release_line(
        connection: DbConnection, identifier: UUID, position: int, allocation: str
    ) -> Cursor[Row]:
        """Освобождает либо потребляет только позицию в состоянии RESERVED.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param position: Порядковый номер изображения в галерее.
        :param allocation: Состояние выделенного резерва позиции заказа.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE order_lines SET allocation=%s WHERE order_id=%s AND position=%s AND allocation='RESERVED'",
            (allocation, identifier, position),
        )

    @staticmethod
    def restore_product(connection: DbConnection, identifier: UUID, quantity: int) -> Cursor[Row]:
        """Восстанавливает оплаченное количество; блокировка защищает от повторного возврата.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param quantity: Количество единиц позиции; для питомца всегда одна.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE products SET stock=stock+%s,version=version+1 WHERE id=%s", (quantity, identifier)
        )

    @staticmethod
    def restore_line(connection: DbConnection, identifier: UUID, position: int) -> Cursor[Row]:
        """Отмечает восстановление потреблённого товара под блокировкой заказа.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param position: Порядковый номер изображения в галерее.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE order_lines SET allocation='RELEASED' WHERE order_id=%s AND position=%s AND allocation='CONSUMED'",
            (identifier, position),
        )

    @staticmethod
    def set_expired(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Сохраняет разрешённое сервисом истечение неоплаченного заказа.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE store_orders SET status='expired',payment_status='EXPIRED',complete=TRUE,version=version+1 WHERE id=%s",
            (identifier,),
        )

    @staticmethod
    def overdue(connection: DbConnection) -> Cursor[Row]:
        """Выбирает просроченные MIXED-заказы, не ожидая конкурентной оплаты.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            """SELECT * FROM store_orders WHERE order_kind='MIXED' AND status='placed' AND payment_status='UNPAID'
               AND payment_expires_at<=CURRENT_TIMESTAMP ORDER BY id FOR UPDATE SKIP LOCKED"""
        )

    @staticmethod
    def refund(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Переводит успешные платежи в REFUNDED под блокировкой заказа.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
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
        """Сохраняет переход состояния, предварительно проверенный сервисом.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param target: Целевое состояние жизненного цикла.
        :param payment_status: Состояние оплаты заказа.
        :param ship_date: Дата отправки заказа.
        :return: Результат операции типа Cursor[Row].
        """
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
        """Удаляет попытки оплаты перед удалением защищённого связями заказа.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute("DELETE FROM payments WHERE order_id=%s", (identifier,))

    @staticmethod
    def delete_lines(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Удаляет снимки позиций только для разрешённого к удалению заказа.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute("DELETE FROM order_lines WHERE order_id=%s", (identifier,))

    @staticmethod
    def delete_parent(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Удаляет заблокированный заказ после зависимых записей.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute("DELETE FROM store_orders WHERE id=%s", (identifier,))
