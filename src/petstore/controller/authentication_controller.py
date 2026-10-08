"""Авторизация и передача HTTP-команд сервисам приложения."""

from typing import cast

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.model.requests import (
    LoginRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses


class AuthenticationController:
    """Вход и восстановление пароля."""

    def login(self, context: RequestContext) -> Response:
        """Проверяет активный аккаунт и возвращает Bearer-токен.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        request = context.validated(LoginRequest, V.login)
        return Responses(context.auth.login(cast(str, request.email), cast(str, request.password)))

    def forgot_password(self, context: RequestContext) -> Response:
        """Создаёт ссылку восстановления с учётом настройки её видимости.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        request = context.validated(PasswordForgotRequest, V.forgot)
        return Responses(context.auth.forgot_password(cast(str, request.email)))

    def reset_password(self, context: RequestContext) -> Response:
        """Передаёт одноразовый код из query и новый пароль из JSON сервису восстановления.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        request = context.validated(PasswordResetRequest, V.reset)
        context.auth.reset_password(context.parameters["code"], cast(str, request.new_password))
        return Response(status_code=204)
