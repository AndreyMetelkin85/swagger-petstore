"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, UploadContext, decode_response
from petstore.controller.media_controller import MediaController
from petstore.model.responses import MediaMetadata

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> MediaController:
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа MediaController.
    """
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
    """Загрузить проверенное фото (10 MiB / 40 MP).

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :return: Результат операции типа MediaMetadata.
    """
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
    """Метаданные или изображение.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param resource_id: UUID ресурса из параметра пути.
    :return: Результат операции типа MediaMetadata.
    """
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
    """Удалить неиспользуемое фото.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param resource_id: UUID ресурса из параметра пути.
    :return: HTTP-ответ с публичными данными и статусом операции.
    """
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
    """Метаданные или изображение.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param resource_id: UUID ресурса из параметра пути.
    :return: HTTP-ответ с публичными данными и статусом операции.
    """
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
    """Метаданные или изображение.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param resource_id: UUID ресурса из параметра пути.
    :return: HTTP-ответ с публичными данными и статусом операции.
    """
    context.parameters = {"id": resource_id}
    result = controller.get(context, True)
    return result
