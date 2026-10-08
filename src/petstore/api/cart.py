"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

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
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа CartController.
    """
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
    """Общая корзина.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :return: Результат операции типа Cart.
    """
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
    """Полная замена корзины по версии.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param idempotency_key: UUID из Idempotency-Key, защищающий повтор операции.
    :return: Результат операции типа Cart.
    """
    context.parameters = {"Idempotency-Key": idempotency_key}
    context.body = body
    result = controller.replace(context)
    return decode_response(result, response)
