"""Авторизация и передача HTTP-команд сервисам приложения."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.model.requests import (
    AdminUserUpdateRequest,
    UserUpdateRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses, public_user


class UserController:
    """Собственный профиль и административное управление аккаунтами."""

    def get_current_user(self, context: RequestContext) -> Response:
        """Возвращает публичный профиль авторизованного пользователя.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return Responses(public_user(context.authorize("USER", "ADMIN")))

    def update_current_user(self, context: RequestContext) -> Response:
        """Применяет частичное изменение собственного профиля.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        user = context.authorize("USER", "ADMIN")
        return Responses(
            public_user(
                context.auth.user_data.update_user(user, context.validated(UserUpdateRequest, V.user_update))
            )
        )

    def list_users(self, context: RequestContext) -> Response:
        """Возвращает публичные профили пользователей только администратору.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        return Responses([public_user(user) for user in context.auth.user_data.find_all()])

    def get_user_by_id(self, context: RequestContext) -> Response:
        """Возвращает целевой аккаунт после проверки роли ADMIN.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        return Responses(public_user(context.auth.required_user(context.identifier("userId"))))

    def update_user_by_id(self, context: RequestContext) -> Response:
        """Заменяет поля аккаунта, разрешённые для редактирования администратором.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        request = context.validated(AdminUserUpdateRequest, V.admin_update)
        return Responses(
            public_user(context.auth.user_data.update_user_as_admin(context.identifier("userId"), request))
        )

    def delete_user_by_id(self, context: RequestContext) -> Response:
        """Удаляет аккаунт с проверкой защищённых пользователей и истории заказов.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("ADMIN")
        context.auth.user_data.delete_user(actor, context.identifier("userId"))
        return Response(status_code=204)
