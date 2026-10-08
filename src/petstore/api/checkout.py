"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Path
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.commerce_order_controller import CommerceOrderController
from petstore.model.commerce import CheckoutCommand, VersionCommand
from petstore.model.enums import OrderStatus
from petstore.model.requests import PaymentRequest
from petstore.model.responses import Payment, StoreOrder

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> CommerceOrderController:
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа CommerceOrderController.
    """
    return cast(CommerceOrderController, context.request.app.state.controllers.checkout)


Controller = Annotated[CommerceOrderController, Depends(get_controller)]


@router.get(
    "/store/orders",
    name="listCommerceOrders",
    operation_id="listCommerceOrders",
    tags=["commerce"],
    response_model=list[StoreOrder],
    response_model_exclude_unset=True,
    status_code=200,
)
def list_commerce_orders(
    context: Context,
    controller: Controller,
    response: Response,
) -> list[StoreOrder]:
    """История заказов.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :return: Результат операции типа list[StoreOrder].
    """
    result = controller.list_orders(context)
    return decode_response(result, response)


@router.post(
    "/store/orders",
    name="createCommerceOrder",
    operation_id="createCommerceOrder",
    tags=["commerce"],
    response_model=StoreOrder,
    response_model_exclude_unset=True,
    status_code=200,
)
def create_commerce_order(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[CheckoutCommand, BeforeValidator(CheckoutCommand.from_wire), Body()],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> StoreOrder:
    """Черновик из версии корзины.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param idempotency_key: UUID из Idempotency-Key, защищающий повтор операции.
    :return: Результат операции типа StoreOrder.
    """
    context.parameters = {"Idempotency-Key": idempotency_key}
    context.body = body
    result = controller.create(context)
    return decode_response(result, response)


@router.get(
    "/store/orders/{id}",
    name="getCommerceOrder",
    operation_id="getCommerceOrder",
    tags=["commerce"],
    response_model=StoreOrder,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_commerce_order(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> StoreOrder:
    """Состав заказа и снимок доставки.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param resource_id: UUID ресурса из параметра пути.
    :return: Результат операции типа StoreOrder.
    """
    context.parameters = {"id": resource_id}
    result = controller.get(context)
    return decode_response(result, response)


@router.delete(
    "/store/orders/{id}",
    name="deleteCommerceOrder",
    operation_id="deleteCommerceOrder",
    tags=["commerce"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=204,
)
def delete_commerce_order(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> Response:
    """Очистить черновик или терминальный заказ.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param resource_id: UUID ресурса из параметра пути.
    :return: HTTP-ответ с публичными данными и статусом операции.
    """
    context.parameters = {"id": resource_id}
    result = controller.delete(context)
    return result


@router.post(
    "/store/orders/{id}/place",
    name="placeCommerceOrder",
    operation_id="placeCommerceOrder",
    tags=["commerce"],
    response_model=StoreOrder,
    response_model_exclude_unset=True,
    status_code=200,
)
def place_commerce_order(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> StoreOrder:
    """Действие заказа: place.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param resource_id: UUID ресурса из параметра пути.
    :param idempotency_key: UUID из Idempotency-Key, защищающий повтор операции.
    :return: Результат операции типа StoreOrder.
    """
    context.parameters = {"id": resource_id, "Idempotency-Key": idempotency_key}
    context.body = body
    result = controller.place(context)
    return decode_response(result, response)


@router.post(
    "/store/orders/{id}/approve",
    name="approveCommerceOrder",
    operation_id="approveCommerceOrder",
    tags=["commerce"],
    response_model=StoreOrder,
    response_model_exclude_unset=True,
    status_code=200,
)
def approve_commerce_order(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> StoreOrder:
    """Действие заказа: approve.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param resource_id: UUID ресурса из параметра пути.
    :return: Результат операции типа StoreOrder.
    """
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.transition(context, OrderStatus.APPROVED)
    return decode_response(result, response)


@router.post(
    "/store/orders/{id}/ship",
    name="shipCommerceOrder",
    operation_id="shipCommerceOrder",
    tags=["commerce"],
    response_model=StoreOrder,
    response_model_exclude_unset=True,
    status_code=200,
)
def ship_commerce_order(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> StoreOrder:
    """Действие заказа: ship.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param resource_id: UUID ресурса из параметра пути.
    :return: Результат операции типа StoreOrder.
    """
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.transition(context, OrderStatus.SHIPPED)
    return decode_response(result, response)


@router.post(
    "/store/orders/{id}/deliver",
    name="deliverCommerceOrder",
    operation_id="deliverCommerceOrder",
    tags=["commerce"],
    response_model=StoreOrder,
    response_model_exclude_unset=True,
    status_code=200,
)
def deliver_commerce_order(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> StoreOrder:
    """Действие заказа: deliver.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param resource_id: UUID ресурса из параметра пути.
    :return: Результат операции типа StoreOrder.
    """
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.transition(context, OrderStatus.DELIVERED)
    return decode_response(result, response)


@router.post(
    "/store/orders/{id}/cancel",
    name="cancelCommerceOrder",
    operation_id="cancelCommerceOrder",
    tags=["commerce"],
    response_model=StoreOrder,
    response_model_exclude_unset=True,
    status_code=200,
)
def cancel_commerce_order(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> StoreOrder:
    """Действие заказа: cancel.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param resource_id: UUID ресурса из параметра пути.
    :return: Результат операции типа StoreOrder.
    """
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.transition(context, OrderStatus.CANCELLED)
    return decode_response(result, response)


@router.get(
    "/store/orders/{id}/payments",
    name="listCommercePayments",
    operation_id="listCommercePayments",
    tags=["commerce"],
    response_model=list[Payment],
    response_model_exclude_unset=True,
    status_code=200,
)
def list_commerce_payments(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> list[Payment]:
    """История общей оплаты.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param resource_id: UUID ресурса из параметра пути.
    :return: Результат операции типа list[Payment].
    """
    context.parameters = {"id": resource_id}
    result = controller.list_payments(context)
    return decode_response(result, response)


@router.post(
    "/store/orders/{id}/payments",
    name="createCommercePayment",
    operation_id="createCommercePayment",
    tags=["commerce"],
    response_model=Payment,
    response_model_exclude_unset=True,
    status_code=200,
)
def create_commerce_payment(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[PaymentRequest, BeforeValidator(PaymentRequest.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> Payment:
    """Единая оплата состава заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param resource_id: UUID ресурса из параметра пути.
    :param idempotency_key: UUID из Idempotency-Key, защищающий повтор операции.
    :return: Результат операции типа Payment.
    """
    context.parameters = {"id": resource_id, "Idempotency-Key": idempotency_key}
    context.body = body
    result = controller.create_payment(context)
    return decode_response(result, response)
