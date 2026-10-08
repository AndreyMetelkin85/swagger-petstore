"""Авторизация и передача HTTP-команд сервисам приложения."""

from typing import cast

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.model.requests import (
    LoginRequest,
    RegisterRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses, public_user


class RegistrationController:
    """Регистрация аккаунта и одноразовое подтверждение."""

    def register(self, context: RequestContext) -> Response:
        """Создаёт аккаунт, ожидающий подтверждения регистрации.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        request = context.validated(RegisterRequest, V.registration)
        return Responses(context.auth.register(request), status_code=201)

    def confirm(self, context: RequestContext) -> Response:
        """Подтверждает аккаунт по UUID из пути и одноразовому коду из query.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return Responses(
            public_user(context.auth.confirm(context.identifier("userId"), context.parameters["code"]))
        )

    def resend_confirmation(self, context: RequestContext) -> Response:
        """Перевыпускает ссылку неподтверждённого аккаунта; предыдущие ссылки становятся недействительными.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        request = context.validated(LoginRequest, V.login)
        return Responses(
            context.auth.resend_confirmation(cast(str, request.email), cast(str, request.password))
        )
