"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.registration_controller import RegistrationController
from petstore.model.requests import LoginRequest, RegisterRequest
from petstore.model.responses import ConfirmationLinkResponse, RegistrationResponse, User

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> RegistrationController:
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа RegistrationController.
    """
    return cast(RegistrationController, context.request.app.state.controllers.registration)


Controller = Annotated[RegistrationController, Depends(get_controller)]


@router.post(
    "/auth/register",
    name="register",
    operation_id="register",
    tags=["legacy"],
    response_model=RegistrationResponse,
    response_model_exclude_unset=True,
    status_code=201,
)
def register(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[RegisterRequest, BeforeValidator(RegisterRequest.from_wire), Body()],
) -> RegistrationResponse:
    """Регистрация пользователя.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :return: Результат операции типа RegistrationResponse.
    """
    context.body = body
    result = controller.register(context)
    return decode_response(result, response)


@router.get(
    "/auth/confirm/{userId}",
    name="confirm",
    operation_id="confirm",
    tags=["legacy"],
    response_model=User,
    response_model_exclude_unset=True,
    status_code=200,
)
def confirm(
    context: Context,
    controller: Controller,
    response: Response,
    user_id: Annotated[UUID, Path(alias="userId")],
    code: Annotated[str, Query(alias="code")],
) -> User:
    """Подтверждение регистрации.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param user_id: UUID целевого пользователя.
    :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
    :return: Результат операции типа User.
    """
    context.parameters = {"userId": user_id, "code": code}
    result = controller.confirm(context)
    return decode_response(result, response)


@router.post(
    "/auth/confirmation/resend",
    name="resendConfirmation",
    operation_id="resendConfirmation",
    tags=["legacy"],
    response_model=ConfirmationLinkResponse,
    response_model_exclude_unset=True,
    status_code=200,
)
def resend_confirmation(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[LoginRequest, BeforeValidator(LoginRequest.from_wire), Body()],
) -> ConfirmationLinkResponse:
    """Повторная отправка ссылки подтверждения.

    Учётные данные сохраняются в context.body и передаются контроллеру.
    Сервис проверяет аккаунт, заменяет код и отправляет письмо; прежняя ссылка недействительна.
    HTTP-статус переносится из результата контроллера, JSON проверяется моделью FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Email и пароль, разобранные из JSON в LoginRequest.
    :return: Результат операции типа ConfirmationLinkResponse.
    """
    context.body = body
    result = controller.resend_confirmation(context)
    return decode_response(result, response)
