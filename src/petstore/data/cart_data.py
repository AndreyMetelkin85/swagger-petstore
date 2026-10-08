"""Хранение данных PostgreSQL и транзакционные SQL-операции."""

from decimal import Decimal
from uuid import UUID

from psycopg import Cursor

from petstore.data.catalog_data import CatalogData
from petstore.data.database import DbConnection, Row
from petstore.data.user_data import UserData


class CartData:
    """SQL корзины; версии, доступность и повторные команды проверяет CartService."""

    @staticmethod
    def lock(connection: DbConnection, user_id: UUID) -> Row:
        """Блокирует строки пользователя и корзины для согласования удаления, изменения и оформления.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param user_id: UUID целевого пользователя.
        :return: Результат операции типа Row.
        """
        UserData.locked_user(connection, user_id)
        connection.execute("INSERT INTO carts (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        row = connection.execute("SELECT * FROM carts WHERE user_id=%s FOR UPDATE", (user_id,)).fetchone()
        assert row is not None
        return row

    @staticmethod
    def item(connection: DbConnection, kind: str, identifier: UUID) -> Row | None:
        """Читает ссылку каталога, сохраняя отсутствующие и неопубликованные позиции корзины.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Row | None.
        """
        return connection.execute(
            f"SELECT * FROM {CatalogData.table(kind)} WHERE id=%s", (identifier,)
        ).fetchone()

    @staticmethod
    def lines(connection: DbConnection, user_id: UUID) -> Cursor[Row]:
        """Читает позиции и сохранённые цены в детерминированном порядке.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param user_id: UUID целевого пользователя.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "SELECT * FROM cart_lines WHERE user_id=%s ORDER BY item_type,item_id", (user_id,)
        )

    @staticmethod
    def clear(connection: DbConnection, user_id: UUID) -> None:
        """Удаляет позиции заблокированной корзины перед полной заменой.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param user_id: UUID целевого пользователя.
        :return: Ничего не возвращает.
        """
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
        """Сохраняет ссылку на позицию и цену, рассчитанную сервисом.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param user_id: UUID целевого пользователя.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param quantity: Количество единиц позиции; для питомца всегда одна.
        :param name: Имя поля, параметра или ресурса текущей операции.
        :param price: Цена в рублях с точностью до копейки.
        :return: Ничего не возвращает.
        """
        connection.execute(
            "INSERT INTO cart_lines (user_id,item_type,item_id,quantity,name_snapshot,price_snapshot) VALUES (%s,%s,%s,%s,%s,%s)",
            (user_id, kind, identifier, quantity, name, price),
        )

    @staticmethod
    def bump_version(connection: DbConnection, user_id: UUID) -> Cursor[Row]:
        """Увеличивает версию успешно проверенной корзины.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param user_id: UUID целевого пользователя.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE carts SET version=version+1,updated_at=CURRENT_TIMESTAMP WHERE user_id=%s RETURNING *",
            (user_id,),
        )
