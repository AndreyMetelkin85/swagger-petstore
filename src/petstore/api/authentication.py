"""Authentication routes with native typed FastAPI parameters and preserved operation IDs."""

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
    """Inject this application's authentication controller without module-global dependencies."""
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
    """Запрос восстановления пароля."""
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
    """Сброс пароля."""
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
    """Авторизация пользователя."""
    context.body = body
    result = controller.login(context)
    return decode_response(result, response)
