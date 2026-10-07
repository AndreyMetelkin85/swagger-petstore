"""Cart routes with native typed FastAPI parameters and preserved operation IDs."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.cart_controller import CartController
from petstore.model.commerce import CartCommand
from petstore.model.responses import Cart

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> CartController:
    """Inject this application's cart controller without module-global dependencies."""
    return cast(CartController, context.request.app.state.controllers.cart)


Controller = Annotated[CartController, Depends(get_controller)]


@router.get(
    "/store/cart",
    name="getCart",
    operation_id="getCart",
    tags=["commerce"],
    response_model=Cart,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_cart(
    context: Context,
    controller: Controller,
    response: Response,
) -> Cart:
    """Общая корзина."""
    result = controller.get(context)
    return decode_response(result, response)


@router.put(
    "/store/cart",
    name="replaceCart",
    operation_id="replaceCart",
    tags=["commerce"],
    response_model=Cart,
    response_model_exclude_unset=True,
    status_code=200,
)
def replace_cart(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[CartCommand, BeforeValidator(CartCommand.from_wire), Body()],
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Cart:
    """Полная замена корзины по версии."""
    context.parameters = {"Idempotency-Key": idempotency_key}
    context.body = body
    result = controller.replace(context)
    return decode_response(result, response)
