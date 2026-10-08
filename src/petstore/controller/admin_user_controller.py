"""Авторизация и передача HTTP-команд сервисам приложения."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.utils.responses import Responses, public_user


class AdminUserController:
    """Блокировка и восстановление пользователей отдельно от редактирования профиля."""

    def block_user(self, context: RequestContext) -> Response:
        """Блокирует пользователя и отзывает ранее выданные токены доступа.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("ADMIN")
        return Responses(public_user(context.auth.set_blocked(actor, context.identifier("userId"), True)))

    def unblock_user(self, context: RequestContext) -> Response:
        """Восстанавливает состояние подтверждения заблокированного аккаунта.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("ADMIN")
        return Responses(public_user(context.auth.set_blocked(actor, context.identifier("userId"), False)))
