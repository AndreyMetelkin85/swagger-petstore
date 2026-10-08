"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

from typing import Annotated, cast

from fastapi import APIRouter, Body, Depends
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute
from petstore.controller.telemetry_controller import TelemetryController
from petstore.model.commerce import TelemetryCommand

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> TelemetryController:
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа TelemetryController.
    """
    return cast(TelemetryController, context.request.app.state.controllers.telemetry)


Controller = Annotated[TelemetryController, Depends(get_controller)]


@router.post(
    "/telemetry/client-events",
    name="clientEvents",
    operation_id="clientEvents",
    tags=["commerce"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=204,
)
def client_events(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[TelemetryCommand, BeforeValidator(TelemetryCommand.from_wire), Body()],
) -> Response:
    """Обезличенные события (allowlist).

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :return: HTTP-ответ с публичными данными и статусом операции.
    """
    context.body = body
    result = controller.client_events(context)
    return result
