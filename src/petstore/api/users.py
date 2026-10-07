"""Users routes with native typed FastAPI parameters and preserved operation IDs."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.user_controller import UserController
from petstore.model.requests import AdminUserUpdateRequest, UserUpdateRequest
from petstore.model.responses import User

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> UserController:
    """Inject this application's users controller without module-global dependencies."""
    return cast(UserController, context.request.app.state.controllers.users)


Controller = Annotated[UserController, Depends(get_controller)]


@router.get(
    "/user/me",
    name="getCurrentUser",
    operation_id="getCurrentUser",
    tags=["legacy"],
    response_model=User,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_current_user(
    context: Context,
    controller: Controller,
    response: Response,
) -> User:
    """Получение профиля."""
    result = controller.get_current_user(context)
    return decode_response(result, response)


@router.put(
    "/user/me",
    name="updateCurrentUser",
    operation_id="updateCurrentUser",
    tags=["legacy"],
    response_model=User,
    response_model_exclude_unset=True,
    status_code=200,
)
def update_current_user(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[UserUpdateRequest, BeforeValidator(UserUpdateRequest.from_wire), Body()],
) -> User:
    """Обновление профиля."""
    context.body = body
    result = controller.update_current_user(context)
    return decode_response(result, response)


@router.get(
    "/users",
    name="listUsers",
    operation_id="listUsers",
    tags=["legacy"],
    response_model=list[User],
    response_model_exclude_unset=True,
    status_code=200,
)
def list_users(
    context: Context,
    controller: Controller,
    response: Response,
) -> list[User]:
    """Получение списка пользователей."""
    result = controller.list_users(context)
    return decode_response(result, response)


@router.get(
    "/users/{userId}",
    name="getUserById",
    operation_id="getUserById",
    tags=["legacy"],
    response_model=User,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_user_by_id(
    context: Context,
    controller: Controller,
    response: Response,
    user_id: Annotated[UUID, Path(alias="userId")],
) -> User:
    """Получение пользователя."""
    context.parameters = {"userId": user_id}
    result = controller.get_user_by_id(context)
    return decode_response(result, response)


@router.put(
    "/users/{userId}",
    name="updateUserById",
    operation_id="updateUserById",
    tags=["legacy"],
    response_model=User,
    response_model_exclude_unset=True,
    status_code=200,
)
def update_user_by_id(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[AdminUserUpdateRequest, BeforeValidator(AdminUserUpdateRequest.from_wire), Body()],
    user_id: Annotated[UUID, Path(alias="userId")],
) -> User:
    """Обновление пользователя."""
    context.parameters = {"userId": user_id}
    context.body = body
    result = controller.update_user_by_id(context)
    return decode_response(result, response)


@router.delete(
    "/users/{userId}",
    name="deleteUserById",
    operation_id="deleteUserById",
    tags=["legacy"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=204,
)
def delete_user_by_id(
    context: Context,
    controller: Controller,
    response: Response,
    user_id: Annotated[UUID, Path(alias="userId")],
) -> Response:
    """Удаление пользователя."""
    context.parameters = {"userId": user_id}
    result = controller.delete_user_by_id(context)
    return result
