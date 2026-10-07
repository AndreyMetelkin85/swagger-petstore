"""Media routes with native typed FastAPI parameters and preserved operation IDs."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, UploadContext, decode_response
from petstore.controller.media_controller import MediaController
from petstore.model.responses import MediaMetadata

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> MediaController:
    """Inject this application's media controller without module-global dependencies."""
    return cast(MediaController, context.request.app.state.controllers.media)


Controller = Annotated[MediaController, Depends(get_controller)]


@router.post(
    "/media",
    name="uploadMedia",
    operation_id="uploadMedia",
    tags=["commerce"],
    response_model=MediaMetadata,
    response_model_exclude_unset=True,
    status_code=201,
)
def upload_media(
    context: UploadContext,
    controller: Controller,
    response: Response,
) -> MediaMetadata:
    """Загрузить проверенное фото (10 MiB / 40 MP)."""
    result = controller.upload(context)
    return decode_response(result, response)


@router.get(
    "/media/{id}",
    name="getMedia",
    operation_id="getMedia",
    tags=["commerce"],
    response_model=MediaMetadata,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_media(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> MediaMetadata:
    """Метаданные или изображение."""
    context.parameters = {"id": resource_id}
    result = controller.get(context)
    return decode_response(result, response)


@router.delete(
    "/media/{id}",
    name="deleteMedia",
    operation_id="deleteMedia",
    tags=["commerce"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=204,
)
def delete_media(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> Response:
    """Удалить неиспользуемое фото."""
    context.parameters = {"id": resource_id}
    result = controller.delete(context)
    return result


@router.get(
    "/media/{id}/image",
    name="getMediaImage",
    operation_id="getMediaImage",
    tags=["commerce"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_media_image(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> Response:
    """Метаданные или изображение."""
    context.parameters = {"id": resource_id}
    result = controller.get(context, False)
    return result


@router.get(
    "/media/{id}/thumb",
    name="getMediaThumb",
    operation_id="getMediaThumb",
    tags=["commerce"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_media_thumb(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> Response:
    """Метаданные или изображение."""
    context.parameters = {"id": resource_id}
    result = controller.get(context, True)
    return result
