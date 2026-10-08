"""Хранение данных PostgreSQL и транзакционные SQL-операции."""

import json
from typing import Any, cast
from uuid import UUID, uuid4

from petstore.data.database import Database, Row
from petstore.model.requests import PetCreateRequest, PetUpdateRequest
from petstore.service.exceptions import PetException


class PetData:
    """Каталог PostgreSQL с совместимым хранением вложенных JSON-объектов."""

    def __init__(self, database: Database) -> None:
        """Сохраняет общий пул соединений для операций репозитория.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.database = database

    @staticmethod
    def public(row: Row) -> Row:
        """Преобразует строку питомца в действующий формат ответа.

        :param row: Строка базы данных для обработки или преобразования.
        :return: Результат операции типа Row.
        """
        result = {
            "id": row["id"],
            "name": row["name"],
            "category": json.loads(row["category_json"]),
            "photoUrls": json.loads(row["photo_urls_json"]),
            "tags": json.loads(row["tags_json"]),
            "status": row["status"],
            "price": row["price"],
            "currency": "RUB",
            "version": row["version"],
        }
        return {key: value for key, value in result.items() if value is not None}

    def get_pet_by_id(self, pet_id: UUID) -> Row:
        """Возвращает публичного питомца либо ошибку 404 этой операции.

        :param pet_id: UUID питомца.
        :return: Результат операции типа Row.
        """
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM pets WHERE id = %s AND publication_status='PUBLISHED'", (pet_id,)
            ).fetchone()
            if row is None:
                raise PetException(404, "PET_NOT_FOUND", "Pet was not found")
            return self.public(row)

    def find_pet_by_status(self, statuses: str) -> list[Row]:
        """Ищет питомцев по доступности, перечисленной через запятую.

        :param statuses: Разрешённые состояния для фильтра поиска.
        :return: Результат операции типа list[Row].
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pets WHERE publication_status='PUBLISHED' AND status::text = ANY(%s) ORDER BY id",
                (statuses.split(","),),
            ).fetchall()
            return [self.public(row) for row in rows]

    def find_pet_by_tags(self, tags: list[str]) -> list[Row]:
        """Возвращает каждого подходящего питомца один раз в порядке UUID.

        :param tags: Теги питомца для поиска.
        :return: Результат операции типа list[Row].
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pets WHERE publication_status='PUBLISHED' ORDER BY id"
            ).fetchall()
            result: list[Row] = []
            for row in rows:
                pet = self.public(row)
                pet_tags = cast(list[Row], pet["tags"] or [])
                if any(tag.get("name") in tags for tag in pet_tags):
                    result.append(pet)
            return result

    @staticmethod
    def nested(request: PetCreateRequest) -> tuple[str, str, str]:
        """Назначает отсутствующие UUID вложенным объектам и сериализует JSON-столбцы.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа tuple[str, str, str].
        """
        category: dict[str, Any] | None = None
        if request.category:
            category = {"id": str(request.category.id or uuid4()), "name": request.category.name}
        tags = [{"id": str(tag.id or uuid4()), "name": tag.name} for tag in request.tags or [] if tag]
        return (
            json.dumps(category, ensure_ascii=False),
            json.dumps(request.photo_urls or [], ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False),
        )

    def create_pet(self, request: PetCreateRequest) -> Row:
        """Создаёт питомца с UUID базы данных и нулевой версией.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Row.
        """
        category, urls, tags = self.nested(request)
        with self.database.connect() as connection:
            row = connection.execute(
                """INSERT INTO pets (category_json, name, photo_urls_json, tags_json, status, price)
                   VALUES (%s, %s, %s, %s, %s::pet_status, %s) RETURNING *""",
                (category, request.name, urls, tags, request.status or "available", request.price),
            ).fetchone()
            assert row is not None
            return self.public(row)

    def update_pet(self, pet_id: UUID, request: PetUpdateRequest) -> Row:
        """Согласует изменения и отклоняет старую версию либо ручное изменение резерва.

        :param pet_id: UUID питомца.
        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Row.
        """
        with self.database.connect() as connection:
            current = connection.execute("SELECT * FROM pets WHERE id = %s FOR UPDATE", (pet_id,)).fetchone()
            if current is None:
                raise PetException(404, "PET_NOT_FOUND", "Pet was not found")
            if request.version != current["version"]:
                raise PetException(
                    409, "PET_VERSION_CONFLICT", "Pet was changed by another request; reload it and retry"
                )
            from petstore.data.order_data import OrderData

            active = OrderData.has_active_order(connection, pet_id)
            if request.status is not None and active:
                raise PetException(409, "PET_HAS_ACTIVE_ORDER", "Pet status is managed by its active order")
            category, urls, tags = self.nested(request)
            row = connection.execute(
                """UPDATE pets SET category_json = %s, name = %s, photo_urls_json = %s, tags_json = %s,
                   status = %s::pet_status, price = %s, version = version + 1
                   WHERE id = %s AND version = %s RETURNING *""",
                (
                    category,
                    request.name,
                    urls,
                    tags,
                    request.status or current["status"],
                    request.price,
                    pet_id,
                    request.version,
                ),
            ).fetchone()
            assert row is not None
            return self.public(row)

    def delete_pet_if_unused(self, pet_id: UUID) -> None:
        """Удаляет питомца только при отсутствии ссылок из черновиков и истории заказов.

        :param pet_id: UUID питомца.
        :return: Ничего не возвращает.
        """
        with self.database.connect() as connection:
            if (
                connection.execute("SELECT id FROM pets WHERE id = %s FOR UPDATE", (pet_id,)).fetchone()
                is None
            ):
                raise PetException(404, "PET_NOT_FOUND", "Pet was not found")
            if connection.execute(
                """SELECT 1 WHERE EXISTS (SELECT 1 FROM store_orders WHERE pet_id=%s)
                   OR EXISTS (SELECT 1 FROM order_lines WHERE item_type='pet' AND item_id=%s)""",
                (pet_id, pet_id),
            ).fetchone():
                raise PetException(409, "PET_HAS_ORDERS", "Pet with order history cannot be deleted")
            connection.execute("DELETE FROM catalog_images WHERE pet_id=%s", (pet_id,))
            connection.execute("DELETE FROM pets WHERE id = %s", (pet_id,))
