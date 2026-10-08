"""Хранение данных PostgreSQL и транзакционные SQL-операции."""

import json
from typing import Any, LiteralString, cast
from uuid import UUID

from psycopg import Cursor, sql

from petstore.data.database import DbConnection, Row
from petstore.model.commerce import ImageReference
from petstore.service.exceptions import ApiException


class CatalogData:
    """SQL каталога и упорядоченные блокировки в транзакции вызывающего сервиса."""

    @staticmethod
    def table(kind: str) -> LiteralString:
        """Возвращает имя таблицы из разрешённого списка без SQL-подстановки пользовательского ввода.

        :param kind: Тип позиции или категории: товар либо питомец.
        :return: Результат операции типа LiteralString.
        """
        if kind not in {"product", "pet"}:
            raise ApiException(422, "VALIDATION_ERROR", "Unknown item kind")
        return "products" if kind == "product" else "pets"

    @classmethod
    def locked(cls, connection: DbConnection, kind: str, identifier: UUID) -> Row:
        """Блокирует карточку в уже открытой транзакции вызывающего сервиса.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Row.
        """
        row = connection.execute(
            f"SELECT * FROM {cls.table(kind)} WHERE id = %s FOR UPDATE", (identifier,)
        ).fetchone()
        if row is None:
            raise ApiException(
                404,
                "PRODUCT_NOT_FOUND" if kind == "product" else "PET_NOT_FOUND",
                "Catalog item was not found",
            )
        return row

    @staticmethod
    def gallery(connection: DbConnection, kind: str, identifier: UUID) -> list[Row]:
        """Возвращает порядок изображений и обложку без путей хранения.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа list[Row].
        """
        column = "product_id" if kind == "product" else "pet_id"
        rows = connection.execute(
            f"SELECT media_id, position, alt, is_cover FROM catalog_images WHERE {column} = %s ORDER BY position",
            (identifier,),
        ).fetchall()
        return [
            {
                "mediaId": row["media_id"],
                "position": row["position"],
                "alt": row["alt"],
                "isCover": row["is_cover"],
                "imageUrl": f"/api/v3/media/{row['media_id']}/image",
                "thumbUrl": f"/api/v3/media/{row['media_id']}/thumb",
            }
            for row in rows
        ]

    @classmethod
    def public(cls, connection: DbConnection, kind: str, row: Row) -> Row:
        """Преобразует столбцы карточки в публичный DTO.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param row: Строка базы данных для обработки или преобразования.
        :return: Результат операции типа Row.
        """
        common = {
            "id": row["id"],
            "kind": kind,
            "name": row["name"],
            "description": row["description"],
            "categoryId": row["category_id"],
            "price": row["price"],
            "currency": "RUB",
            "publicationStatus": row["publication_status"],
            "version": row["version"],
            "images": cls.gallery(connection, kind, row["id"]),
        }
        if kind == "product":
            common.update(
                sku=row["sku"],
                brand=row["brand"],
                productType=row["product_type"],
                animalTypes=row["animal_types"],
                feedForm=row["feed_form"],
                lifeStages=row["life_stages"],
                netWeightGrams=row["net_weight_grams"],
                ingredients=row["ingredients"],
                stock=row["stock"],
                reserved=row["reserved"],
                availableQuantity=row["stock"] - row["reserved"],
            )
        else:
            common.update(
                animalType=row["animal_type"],
                breed=row["breed"],
                sex=row["sex"],
                birthDate=row["birth_date"].isoformat() if row["birth_date"] else None,
                status=row["status"],
                photoUrls=json.loads(row["photo_urls_json"]),
            )
        return common

    @staticmethod
    def categories(connection: DbConnection, public: bool, kind: str | None) -> Cursor[Row]:
        """Читает категории с дополнительным фильтром активности.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param public: Ограничивать ли выборку опубликованными и активными данными.
        :param kind: Тип позиции или категории: товар либо питомец.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "SELECT * FROM catalog_categories WHERE (%s = FALSE OR active) AND (%s::text IS NULL OR kind = %s) ORDER BY name, id",
            (public, kind, kind),
        )

    @staticmethod
    def create_category(connection: DbConnection, name: str, kind: str, active: bool) -> Cursor[Row]:
        """Добавляет предварительно проверенную категорию.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param name: Имя поля, параметра или ресурса текущей операции.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param active: Фильтр активности категории.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "INSERT INTO catalog_categories (name,kind,active) VALUES (%s,%s,%s) RETURNING *",
            (name, kind, active),
        )

    @staticmethod
    def lock_category(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Блокирует категорию перед обновлением по версии.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute("SELECT * FROM catalog_categories WHERE id=%s FOR UPDATE", (identifier,))

    @staticmethod
    def update_category(connection: DbConnection, identifier: UUID, name: str, active: bool) -> Cursor[Row]:
        """Сохраняет изменение категории, не удаляя связанные карточки.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param name: Имя поля, параметра или ресурса текущей операции.
        :param active: Фильтр активности категории.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE catalog_categories SET name=%s,active=%s,version=version+1 WHERE id=%s RETURNING *",
            (name, active, identifier),
        )

    @staticmethod
    def share_category(connection: DbConnection, identifier: UUID) -> Cursor[Row]:
        """Удерживает тип и активность категории неизменными на время команды каталога.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute("SELECT * FROM catalog_categories WHERE id=%s FOR SHARE", (identifier,))

    @staticmethod
    def lock_media(connection: DbConnection, media_id: UUID) -> Cursor[Row]:
        """Блокирует изображение от конкурентного удаления.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param media_id: UUID изображения.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute("SELECT id FROM media WHERE id=%s AND NOT deleted FOR UPDATE", (media_id,))

    @staticmethod
    def clear_gallery(connection: DbConnection, kind: str, identifier: UUID) -> Cursor[Row]:
        """Удаляет прежние связи галереи под уже полученными блокировками.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            f"DELETE FROM catalog_images WHERE {'product_id' if kind == 'product' else 'pet_id'}=%s",
            (identifier,),
        )

    @staticmethod
    def add_gallery_image(
        connection: DbConnection,
        kind: str,
        identifier: UUID,
        position: int,
        image: ImageReference,
        is_cover: bool,
    ) -> Cursor[Row]:
        """Сохраняет порядок и выбор обложки, определённые сервисом.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param position: Порядковый номер изображения в галерее.
        :param image: Изображение либо его метаданные.
        :param is_cover: Используется ли изображение как обложка.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            f"INSERT INTO catalog_images ({'product_id' if kind == 'product' else 'pet_id'},media_id,position,alt,is_cover) VALUES (%s,%s,%s,%s,%s)",
            (
                identifier,
                image.media_id,
                position,
                image.alt,
                is_cover,
            ),
        )

    @staticmethod
    def update_card(connection: DbConnection, kind: str, identifier: UUID, fields: Row) -> Cursor[Row]:
        """Обновляет разрешённые поля карточки с параметризованными значениями.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param fields: Проверяемые или изменяемые поля операции.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            sql.SQL("UPDATE {} SET {},version=version+1 WHERE id=%s RETURNING *").format(
                sql.Identifier(CatalogData.table(kind)),
                sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(column)) for column in fields),
            ),
            (*fields.values(), identifier),
        )

    @staticmethod
    def insert_card(connection: DbConnection, kind: str, fields: Row) -> Cursor[Row]:
        """Создаёт подготовленную сервисом карточку без SQL-подстановки значений.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param fields: Проверяемые или изменяемые поля операции.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
                sql.Identifier(CatalogData.table(kind)),
                sql.SQL(",").join(sql.Identifier(column) for column in fields),
                sql.SQL(",").join(sql.Placeholder() for _ in fields),
            ),
            tuple(fields.values()),
        )

    @staticmethod
    def get(connection: DbConnection, kind: str, identifier: UUID) -> Cursor[Row]:
        """Читает карточку; проверка видимости публикации остаётся в сервисе.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(f"SELECT * FROM {CatalogData.table(kind)} WHERE id=%s", (identifier,))

    @staticmethod
    def set_publication(connection: DbConnection, kind: str, identifier: UUID, target: str) -> Cursor[Row]:
        """Сохраняет состояние публикации, разрешённое сервисом.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param target: Целевое состояние жизненного цикла.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            f"UPDATE {CatalogData.table(kind)} SET publication_status=%s,version=version+1 WHERE id=%s RETURNING *",
            (target, identifier),
        )

    @staticmethod
    def set_stock(connection: DbConnection, identifier: UUID, value: int) -> Cursor[Row]:
        """Сохраняет проверенный остаток под блокировкой товара.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "UPDATE products SET stock=%s,version=version+1 WHERE id=%s RETURNING *", (value, identifier)
        )

    @staticmethod
    def audit_stock(
        connection: DbConnection,
        identifier: UUID,
        actor_id: UUID,
        delta: int,
        reason: str,
        before: int,
        value: int,
    ) -> Cursor[Row]:
        """Добавляет неизменяемую запись изменения остатка.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :param actor_id: UUID пользователя, выполняющего операцию.
        :param delta: Изменение остатка относительно текущего значения.
        :param reason: Причина изменения остатка или недоступности позиции.
        :param before: Состояние записи до изменения.
        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :return: Результат операции типа Cursor[Row].
        """
        return connection.execute(
            "INSERT INTO stock_adjustments (product_id,actor_id,delta,reason,before_stock,after_stock) VALUES (%s,%s,%s,%s,%s,%s)",
            (identifier, actor_id, delta, reason, before, value),
        )

    @staticmethod
    def search(
        connection: DbConnection,
        kind: str,
        public: bool,
        query: dict[str, Any],
        page: int,
        size: int,
        category: UUID | None,
        minimum: str | None,
        maximum: str | None,
        ordering: str,
    ) -> tuple[Row, list[Row]]:
        """Выполняет поиск с параметризованными фильтрами и разрешённой сортировкой.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param public: Ограничивать ли выборку опубликованными и активными данными.
        :param query: Текст запроса или разобранные фильтры текущей операции.
        :param page: Номер страницы, начиная с первой.
        :param size: Размер файла для ключа кэша.
        :param category: Данные категории для связи с карточкой.
        :param minimum: Минимальное допустимое значение.
        :param maximum: Максимальное допустимое значение.
        :param ordering: Проверенное SQL-выражение сортировки из разрешённого списка.
        :return: Результат операции типа tuple[Row, list[Row]].
        """
        conditions = [
            "(%s = FALSE OR publication_status='PUBLISHED')",
            "(%s::uuid IS NULL OR category_id=%s)",
            "(%s::numeric IS NULL OR price >= %s::numeric)",
            "(%s::numeric IS NULL OR price <= %s::numeric)",
        ]
        values: list[Any] = [public, category, category, minimum, minimum, maximum, maximum]
        term = str(query.get("q", ""))[:150]
        conditions.append("(name ILIKE %s OR description ILIKE %s)")
        values.extend(["%" + term + "%"] * 2)
        for param, column in (
            ("brand", "brand"),
            ("productType", "product_type"),
            ("feedForm", "feed_form"),
            ("publicationStatus", "publication_status"),
            ("status", "status"),
        ):
            if query.get(param) and (
                (kind == "product" and param != "status")
                or (kind == "pet" and param in {"status", "publicationStatus"})
            ):
                conditions.append(f"{column}=%s")
                values.append(str(query[param]))
        if query.get("animalType"):
            if kind == "product":
                conditions.append("animal_types ? %s")
            else:
                conditions.append("animal_type=%s")
            values.append(str(query["animalType"]))
        where = sql.SQL(" AND ").join(sql.SQL(cast(LiteralString, clause)) for clause in conditions)
        count = connection.execute(
            sql.SQL("SELECT COUNT(*) AS count FROM {} WHERE {}").format(
                sql.Identifier(CatalogData.table(kind)), where
            ),
            tuple(values),
        ).fetchone()
        rows = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE {} ORDER BY {},id LIMIT %s OFFSET %s").format(
                sql.Identifier(CatalogData.table(kind)), where, sql.SQL(cast(LiteralString, ordering))
            ),
            (*values, size, (page - 1) * size),
        ).fetchall()

        assert count is not None
        return count, rows
