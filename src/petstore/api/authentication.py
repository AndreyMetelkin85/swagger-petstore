"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

from typing import Annotated, cast

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.authentication_controller import AuthenticationController
from petstore.model.requests import LoginRequest, PasswordForgotRequest, PasswordResetRequest
from petstore.model.responses import LoginResponse, PasswordResetLinkResponse

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> AuthenticationController:
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа AuthenticationController.
    """
    return cast(AuthenticationController, context.request.app.state.controllers.authentication)


Controller = Annotated[AuthenticationController, Depends(get_controller)]


@router.post(
    "/auth/password/forgot",
    name="forgotPassword",
    operation_id="forgotPassword",
    tags=["legacy"],
    response_model=PasswordResetLinkResponse,
    response_model_exclude_unset=True,
    status_code=200,
)
def forgot_password(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[PasswordForgotRequest, BeforeValidator(PasswordForgotRequest.from_wire), Body()],
) -> PasswordResetLinkResponse:
    """Запрос восстановления пароля.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :return: Результат операции типа PasswordResetLinkResponse.
    """
    context.body = body
    result = controller.forgot_password(context)
    return decode_response(result, response)


@router.post(
    "/auth/password/reset",
    name="resetPassword",
    operation_id="resetPassword",
    tags=["legacy"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=204,
)
def reset_password(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[PasswordResetRequest, BeforeValidator(PasswordResetRequest.from_wire), Body()],
    code: Annotated[str, Query(alias="code")],
) -> Response:
    """Сброс пароля.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
    :return: HTTP-ответ с публичными данными и статусом операции.
    """
    context.parameters = {"code": code}
    context.body = body
    result = controller.reset_password(context)
    return result


@router.post(
    "/auth/login",
    name="login",
    operation_id="login",
    tags=["legacy"],
    response_model=LoginResponse,
    response_model_exclude_unset=True,
    status_code=200,
)
def login(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[LoginRequest, BeforeValidator(LoginRequest.from_wire), Body()],
) -> LoginResponse:
    """Авторизация пользователя.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :return: Результат операции типа LoginResponse.
    """
    context.body = body
    result = controller.login(context)
    return decode_response(result, response)
