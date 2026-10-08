"""Авторизация и передача HTTP-команд сервисам приложения."""

from typing import cast
from uuid import UUID

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.model.commerce import CartCommand
from petstore.service.cart_service import CartService
from petstore.utils.responses import Responses


class CartController:
    """Авторизация HTTP-команд корзины; доступность и повторы проверяет сервис."""

    def __init__(self, database: Database) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.cart = CartService(database)

    def get(self, context: RequestContext) -> Response:
        """Возвращает корзину только авторизованного пользователя.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return Responses(self.cart.get(context.authorize("USER", "ADMIN")))

    def replace(self, context: RequestContext) -> Response:
        """Заменяет собственную корзину с проверкой версии и ключа повторного запроса.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        assert isinstance(context.body, CartCommand)
        return Responses(
            self.cart.replace(
                context.body,
                context.authorize("USER", "ADMIN"),
                cast(UUID | None, context.parameters.get("Idempotency-Key")),
            )
        )
