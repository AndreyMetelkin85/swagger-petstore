"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.order_controller import OrderController
from petstore.model.requests import OrderCreateRequest
from petstore.model.responses import Order

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> OrderController:
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа OrderController.
    """
    return cast(OrderController, context.request.app.state.controllers.orders)


Controller = Annotated[OrderController, Depends(get_controller)]


@router.get(
    "/store/inventory",
    name="getInventory",
    operation_id="getInventory",
    tags=["legacy"],
    response_model=dict[str, int],
    response_model_exclude_unset=True,
    status_code=200,
)
def get_inventory(
    context: Context,
    controller: Controller,
    response: Response,
) -> dict[str, int]:
    """Получение количества заказов по статусам.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :return: Результат операции типа dict[str, int].
    """
    result = controller.get_inventory(context)
    return decode_response(result, response)


@router.get(
    "/store/order",
    name="listOrders",
    operation_id="listOrders",
    tags=["legacy"],
    response_model=list[Order],
    response_model_exclude_unset=True,
    status_code=200,
)
def list_orders(
    context: Context,
    controller: Controller,
    response: Response,
) -> list[Order]:
    """Получение списка заказов.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :return: Результат операции типа list[Order].
    """
    result = controller.list_orders(context)
    return decode_response(result, response)


@router.post(
    "/store/order",
    name="createOrderDraft",
    operation_id="createOrderDraft",
    tags=["legacy"],
    response_model=Order,
    response_model_exclude_unset=True,
    status_code=201,
)
def create_order_draft(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[OrderCreateRequest, BeforeValidator(OrderCreateRequest.from_wire), Body()],
) -> Order:
    """Создание черновика заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :return: Результат операции типа Order.
    """
    context.body = body
    result = controller.create_order_draft(context)
    return decode_response(result, response)


@router.get(
    "/store/order/{orderId}",
    name="getOrderById",
    operation_id="getOrderById",
    tags=["legacy"],
    response_model=Order,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_order_by_id(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
) -> Order:
    """Получение заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :return: Результат операции типа Order.
    """
    context.parameters = {"orderId": order_id}
    result = controller.get_order_by_id(context)
    return decode_response(result, response)


@router.put(
    "/store/order/{orderId}",
    name="updateOrderDraft",
    operation_id="updateOrderDraft",
    tags=["legacy"],
    response_model=Order,
    response_model_exclude_unset=True,
    status_code=200,
)
def update_order_draft(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[OrderCreateRequest, BeforeValidator(OrderCreateRequest.from_wire), Body()],
    order_id: Annotated[UUID, Path(alias="orderId")],
) -> Order:
    """Обновление черновика заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param order_id: UUID заказа.
    :return: Результат операции типа Order.
    """
    context.parameters = {"orderId": order_id}
    context.body = body
    result = controller.update_order_draft(context)
    return decode_response(result, response)


@router.delete(
    "/store/order/{orderId}",
    name="deleteOrder",
    operation_id="deleteOrder",
    tags=["legacy"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=204,
)
def delete_order(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
) -> Response:
    """Удаление заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :return: HTTP-ответ с публичными данными и статусом операции.
    """
    context.parameters = {"orderId": order_id}
    result = controller.delete_order(context)
    return result


@router.post(
    "/store/order/{orderId}/place",
    name="placeOrderDraft",
    operation_id="placeOrderDraft",
    tags=["legacy"],
    response_model=Order,
    response_model_exclude_unset=True,
    status_code=200,
)
def place_order_draft(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
) -> Order:
    """Оформление черновика заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :return: Результат операции типа Order.
    """
    context.parameters = {"orderId": order_id}
    result = controller.place_order_draft(context)
    return decode_response(result, response)


@router.post(
    "/store/order/{orderId}/approve",
    name="approveOrder",
    operation_id="approveOrder",
    tags=["legacy"],
    response_model=Order,
    response_model_exclude_unset=True,
    status_code=200,
)
def approve_order(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
) -> Order:
    """Подтверждение заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :return: Результат операции типа Order.
    """
    context.parameters = {"orderId": order_id}
    result = controller.approve_order(context)
    return decode_response(result, response)


@router.post(
    "/store/order/{orderId}/ship",
    name="shipOrder",
    operation_id="shipOrder",
    tags=["legacy"],
    response_model=Order,
    response_model_exclude_unset=True,
    status_code=200,
)
def ship_order(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
) -> Order:
    """Передача заказа в доставку.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :return: Результат операции типа Order.
    """
    context.parameters = {"orderId": order_id}
    result = controller.ship_order(context)
    return decode_response(result, response)


@router.post(
    "/store/order/{orderId}/deliver",
    name="deliverOrder",
    operation_id="deliverOrder",
    tags=["legacy"],
    response_model=Order,
    response_model_exclude_unset=True,
    status_code=200,
)
def deliver_order(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
) -> Order:
    """Завершение доставки заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :return: Результат операции типа Order.
    """
    context.parameters = {"orderId": order_id}
    result = controller.deliver_order(context)
    return decode_response(result, response)


@router.post(
    "/store/order/{orderId}/cancel",
    name="cancelOrder",
    operation_id="cancelOrder",
    tags=["legacy"],
    response_model=Order,
    response_model_exclude_unset=True,
    status_code=200,
)
def cancel_order(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
) -> Order:
    """Отмена заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :return: Результат операции типа Order.
    """
    context.parameters = {"orderId": order_id}
    result = controller.cancel_order(context)
    return decode_response(result, response)
