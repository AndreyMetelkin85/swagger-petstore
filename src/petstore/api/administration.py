"""Administration routes with native typed FastAPI parameters and preserved operation IDs."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.admin_user_controller import AdminUserController
from petstore.model.responses import User

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> AdminUserController:
    """Inject this application's administration controller without module-global dependencies."""
    return cast(AdminUserController, context.request.app.state.controllers.administration)


Controller = Annotated[AdminUserController, Depends(get_controller)]


@router.post(
    "/admin/users/{userId}/block",
    name="blockUser",
    operation_id="blockUser",
    tags=["legacy"],
    response_model=User,
    response_model_exclude_unset=True,
    status_code=200,
)
def block_user(
    context: Context,
    controller: Controller,
    response: Response,
    user_id: Annotated[UUID, Path(alias="userId")],
) -> User:
    """Блокировка пользователя."""
    context.parameters = {"userId": user_id}
    result = controller.block_user(context)
    return decode_response(result, response)


@router.post(
    "/admin/users/{userId}/unblock",
    name="unblockUser",
    operation_id="unblockUser",
    tags=["legacy"],
    response_model=User,
    response_model_exclude_unset=True,
    status_code=200,
)
def unblock_user(
    context: Context,
    controller: Controller,
    response: Response,
    user_id: Annotated[UUID, Path(alias="userId")],
) -> User:
    """Разблокировка пользователя."""
    context.parameters = {"userId": user_id}
    result = controller.unblock_user(context)
    return decode_response(result, response)
