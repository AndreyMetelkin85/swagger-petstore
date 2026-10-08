"""Авторизация и передача HTTP-команд сервисам приложения."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar, cast
from uuid import UUID

from starlette.requests import Request

from petstore.data.database import Row
from petstore.model.requests import RequestModel
from petstore.service.auth_service import AuthService
from petstore.service.validation_service import Details, ValidationService

Model = TypeVar("Model", bound=RequestModel)


@dataclass
class RequestContext:
    """Контекст HTTP-запроса с авторизацией, параметрами и моделью тела."""

    request: Request
    auth: AuthService
    parameters: Row
    body: RequestModel | None
    upload: tuple[bytes, str, str] | None = None

    def authorize(self, *roles: str) -> Row:
        """Проверяет Bearer-токен и разрешённые роли для текущей операции.

        :param roles: Роли, которым разрешена операция; пустой список разрешает любой авторизованный аккаунт.
        :return: Результат операции типа Row.
        """
        return self.auth.authorize(self.request.headers.get("Authorization"), *roles)

    def identifier(self, name: str) -> UUID:
        """Возвращает UUID, уже проверенный HTTP-адаптером.

        :param name: Имя UUID-параметра, проверенного HTTP-адаптером.
        :return: Результат операции типа UUID.
        """
        return cast(UUID, self.parameters[name])

    def validated(self, model: type[Model], validator: Callable[[Model], Details]) -> Model:
        """Проверяет тип тела и применяет бизнес-валидацию модели запроса.

        :param model: Ожидаемая модель разобранного запроса.
        :param validator: Функция бизнес-валидации, возвращающая ошибки полей.
        :return: Результат операции типа Model.
        """
        assert isinstance(self.body, model)
        ValidationService.ensure(validator(self.body))
        return self.body
