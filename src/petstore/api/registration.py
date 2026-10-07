"""Registration routes with native typed FastAPI parameters and preserved operation IDs."""

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
    """Inject this application's registration controller without module-global dependencies."""
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
    """Регистрация пользователя."""
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
    """Подтверждение регистрации."""
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
    """Повторная отправка ссылки подтверждения."""
    context.body = body
    result = controller.resend_confirmation(context)
    return decode_response(result, response)
