"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.health_controller import HealthController
from petstore.model.responses import HealthResponse

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> HealthController:
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа HealthController.
    """
    return cast(HealthController, context.request.app.state.controllers.health)


Controller = Annotated[HealthController, Depends(get_controller)]


@router.get(
    "/health",
    name="health",
    operation_id="health",
    tags=["legacy"],
    response_model=HealthResponse,
    response_model_exclude_unset=True,
    status_code=200,
)
def health(
    context: Context,
    controller: Controller,
    response: Response,
) -> HealthResponse:
    """Проверка состояния сервиса.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :return: Результат операции типа HealthResponse.
    """
    result = controller.health(context)
    return decode_response(result, response)
