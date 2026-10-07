"""Health routes with native typed FastAPI parameters and preserved operation IDs."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.health_controller import HealthController
from petstore.model.responses import HealthResponse

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> HealthController:
    """Inject this application's health controller without module-global dependencies."""
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
    """Проверка состояния сервиса."""
    result = controller.health(context)
    return decode_response(result, response)
