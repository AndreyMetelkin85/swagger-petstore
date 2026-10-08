"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Path
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.payment_controller import PaymentController
from petstore.model.requests import PaymentRequest
from petstore.model.responses import Payment

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> PaymentController:
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа PaymentController.
    """
    return cast(PaymentController, context.request.app.state.controllers.payments)


Controller = Annotated[PaymentController, Depends(get_controller)]


@router.post(
    "/store/order/{orderId}/payments",
    name="createPayment",
    operation_id="createPayment",
    tags=["legacy"],
    response_model=Payment,
    response_model_exclude_unset=True,
    status_code=200,
)
def create_payment(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[PaymentRequest, BeforeValidator(PaymentRequest.from_wire), Body()],
    order_id: Annotated[UUID, Path(alias="orderId")],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> Payment:
    """Оплата заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param order_id: UUID заказа.
    :param idempotency_key: UUID из Idempotency-Key, защищающий повтор операции.
    :return: Результат операции типа Payment.
    """
    context.parameters = {"orderId": order_id, "Idempotency-Key": idempotency_key}
    context.body = body
    result = controller.create_payment(context)
    return decode_response(result, response)


@router.get(
    "/store/order/{orderId}/payments",
    name="listPayments",
    operation_id="listPayments",
    tags=["legacy"],
    response_model=list[Payment],
    response_model_exclude_unset=True,
    status_code=200,
)
def list_payments(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
) -> list[Payment]:
    """Получение платежей заказа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :return: Результат операции типа list[Payment].
    """
    context.parameters = {"orderId": order_id}
    result = controller.list_payments(context)
    return decode_response(result, response)


@router.get(
    "/store/order/{orderId}/payments/{paymentId}",
    name="getPayment",
    operation_id="getPayment",
    tags=["legacy"],
    response_model=Payment,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_payment(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
    payment_id: Annotated[UUID, Path(alias="paymentId")],
) -> Payment:
    """Получение платежа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :param payment_id: UUID попытки оплаты.
    :return: Результат операции типа Payment.
    """
    context.parameters = {"orderId": order_id, "paymentId": payment_id}
    result = controller.get_payment(context)
    return decode_response(result, response)


@router.delete(
    "/store/order/{orderId}/payments/{paymentId}",
    name="deletePayment",
    operation_id="deletePayment",
    tags=["legacy"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=204,
)
def delete_payment(
    context: Context,
    controller: Controller,
    response: Response,
    order_id: Annotated[UUID, Path(alias="orderId")],
    payment_id: Annotated[UUID, Path(alias="paymentId")],
) -> Response:
    """Удаление неуспешного платежа.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param order_id: UUID заказа.
    :param payment_id: UUID попытки оплаты.
    :return: HTTP-ответ с публичными данными и статусом операции.
    """
    context.parameters = {"orderId": order_id, "paymentId": payment_id}
    result = controller.delete_payment(context)
    return result
