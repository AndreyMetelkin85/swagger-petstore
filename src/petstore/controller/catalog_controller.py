"""Авторизация и передача HTTP-команд сервисам приложения."""

from uuid import UUID

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.model.commerce import (
    CategoryCommand,
    PetCardCommand,
    ProductCommand,
    StockCommand,
    VersionCommand,
)
from petstore.service.catalog_service import CatalogService
from petstore.utils.responses import Responses


class CatalogController:
    """HTTP-команды товаров, питомцев и категорий с общими правилами каталога."""

    def __init__(self, database: Database) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.catalog = CatalogService(database)

    def list_cards(self, context: RequestContext, kind: str, public: bool) -> Response:
        """Возвращает публичные карточки; доступ к неопубликованным требует роли ADMIN.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param public: Ограничивать ли выборку опубликованными и активными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        if not public:
            context.authorize("ADMIN")
        return Responses(self.catalog.find_all(kind, public, dict(context.request.query_params)))

    def get_card(self, context: RequestContext, kind: str, public: bool) -> Response:
        """Возвращает доступную карточку и проверяет административные права при необходимости.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param public: Ограничивать ли выборку опубликованными и активными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        if not public:
            context.authorize("ADMIN")
        return Responses(self.catalog.get(kind, context.identifier("id"), public))

    def save_card(self, context: RequestContext, kind: str, identifier: UUID | None) -> Response:
        """Создаёт или заменяет карточку по команде администратора.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        command = context.body
        assert isinstance(command, (ProductCommand, PetCardCommand))
        return Responses(
            self.catalog.save(command, identifier), status_code=201 if identifier is None else 200
        )

    def publish(self, context: RequestContext, kind: str, target: str) -> Response:
        """Применяет действие публикации с проверкой версии и роли ADMIN.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :param kind: Тип позиции или категории: товар либо питомец.
        :param target: Целевое состояние жизненного цикла.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        assert isinstance(context.body, VersionCommand)
        return Responses(self.catalog.publish(kind, context.identifier("id"), context.body.version, target))

    def adjust_stock(self, context: RequestContext) -> Response:
        """Проверяет ADMIN и передаёт изменение остатка сервису с журналированием операции.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("ADMIN")
        assert isinstance(context.body, StockCommand)
        return Responses(self.catalog.adjust_stock(context.identifier("id"), context.body, actor))

    def categories(self, context: RequestContext, public: bool) -> Response:
        """Возвращает категории, не удаляя товары деактивированных категорий.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :param public: Ограничивать ли выборку опубликованными и активными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        if not public:
            context.authorize("ADMIN")
        return Responses(self.catalog.categories(public, context.request.query_params.get("kind")))

    def save_category(self, context: RequestContext, identifier: UUID | None) -> Response:
        """Создаёт или обновляет категорию с проверкой ADMIN и версии.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :param identifier: UUID целевой записи, уже проверенный вызывающим кодом.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        assert isinstance(context.body, CategoryCommand)
        return Responses(
            self.catalog.save_category(context.body, identifier),
            status_code=201 if identifier is None else 200,
        )
