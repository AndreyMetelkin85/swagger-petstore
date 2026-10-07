"""Payments routes with native typed FastAPI parameters and preserved operation IDs."""

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
    """Inject this application's payments controller without module-global dependencies."""
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
    """Оплата заказа."""
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
    """Получение платежей заказа."""
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
    """Получение платежа."""
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
    """Удаление неуспешного платежа."""
    context.parameters = {"orderId": order_id, "paymentId": payment_id}
    result = controller.delete_payment(context)
    return result
