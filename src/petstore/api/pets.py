"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.pet_controller import PetController
from petstore.model.requests import PetCreateRequest, PetUpdateRequest
from petstore.model.responses import Pet

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> PetController:
    """Возвращает контроллер этого экземпляра приложения через зависимость FastAPI.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа PetController.
    """
    return cast(PetController, context.request.app.state.controllers.pets)


Controller = Annotated[PetController, Depends(get_controller)]


@router.post(
    "/pet",
    name="addPet",
    operation_id="addPet",
    tags=["legacy"],
    response_model=Pet,
    response_model_exclude_unset=True,
    status_code=201,
)
def add_pet(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[PetCreateRequest, BeforeValidator(PetCreateRequest.from_wire), Body()],
) -> Pet:
    """Добавление питомца.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :return: Результат операции типа Pet.
    """
    context.body = body
    result = controller.add_pet(context)
    return decode_response(result, response)


@router.get(
    "/pet/findByStatus",
    name="findPetsByStatus",
    operation_id="findPetsByStatus",
    tags=["legacy"],
    response_model=list[Pet],
    response_model_exclude_unset=True,
    status_code=200,
)
def find_pets_by_status(
    context: Context,
    controller: Controller,
    response: Response,
    status: Annotated[str, Query(alias="status")],
) -> list[Pet]:
    """Поиск питомцев по статусу.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param status: Статус ресурса либо HTTP-ответа согласно операции.
    :return: Результат операции типа list[Pet].
    """
    context.parameters = {"status": status}
    result = controller.find_pets_by_status(context)
    return decode_response(result, response)


@router.get(
    "/pet/findByTags",
    name="findPetsByTags",
    operation_id="findPetsByTags",
    tags=["legacy"],
    response_model=list[Pet],
    response_model_exclude_unset=True,
    status_code=200,
)
def find_pets_by_tags(
    context: Context,
    controller: Controller,
    response: Response,
    tags: Annotated[list[str], Query(alias="tags")],
) -> list[Pet]:
    """Поиск питомцев по тегам.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param tags: Теги питомца для поиска.
    :return: Результат операции типа list[Pet].
    """
    context.parameters = {"tags": tags and [part for value in tags for part in value.split(",")]}
    result = controller.find_pets_by_tags(context)
    return decode_response(result, response)


@router.put(
    "/pet/{petId}",
    name="updatePet",
    operation_id="updatePet",
    tags=["legacy"],
    response_model=Pet,
    response_model_exclude_unset=True,
    status_code=200,
)
def update_pet(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[PetUpdateRequest, BeforeValidator(PetUpdateRequest.from_wire), Body()],
    pet_id: Annotated[UUID, Path(alias="petId")],
) -> Pet:
    """Обновление питомца.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param body: Модель тела запроса после разбора JSON и проверки FastAPI.
    :param pet_id: UUID питомца.
    :return: Результат операции типа Pet.
    """
    context.parameters = {"petId": pet_id}
    context.body = body
    result = controller.update_pet(context)
    return decode_response(result, response)


@router.get(
    "/pet/{petId}",
    name="getPetById",
    operation_id="getPetById",
    tags=["legacy"],
    response_model=Pet,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_pet_by_id(
    context: Context,
    controller: Controller,
    response: Response,
    pet_id: Annotated[UUID, Path(alias="petId")],
) -> Pet:
    """Получение питомца.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param pet_id: UUID питомца.
    :return: Результат операции типа Pet.
    """
    context.parameters = {"petId": pet_id}
    result = controller.get_pet_by_id(context)
    return decode_response(result, response)


@router.delete(
    "/pet/{petId}",
    name="deletePet",
    operation_id="deletePet",
    tags=["legacy"],
    response_model=None,
    response_model_exclude_unset=True,
    status_code=204,
)
def delete_pet(
    context: Context,
    controller: Controller,
    response: Response,
    pet_id: Annotated[UUID, Path(alias="petId")],
) -> Response:
    """Удаление питомца.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :param controller: Контроллер соответствующей операции, предоставленный зависимостью FastAPI.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :param pet_id: UUID питомца.
    :return: HTTP-ответ с публичными данными и статусом операции.
    """
    context.parameters = {"petId": pet_id}
    result = controller.delete_pet(context)
    return result
