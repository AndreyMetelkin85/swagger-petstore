"""Авторизация и передача HTTP-команд сервисам приложения."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.data.pet_data import PetData
from petstore.model.requests import (
    PetCreateRequest,
    PetUpdateRequest,
)
from petstore.service.exceptions import ApiException
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses


class PetController:
    """Публичный просмотр питомцев и административные изменения каталога."""

    def __init__(self, database: Database) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.data = PetData(database)

    def find_pets_by_status(self, context: RequestContext) -> Response:
        """Ищет питомцев по статусам, перечисленным через запятую.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        status = context.parameters["status"]
        if not status or not status.strip():
            raise ApiException(400, "BAD_REQUEST", "Status is required")
        if any(value not in {"available", "pending", "reserved", "sold"} for value in status.split(",")):
            V.ensure([{"field": "status", "message": "Status must be available, pending, reserved or sold"}])
        return Responses(self.data.find_pet_by_status(status))

    def find_pets_by_tags(self, context: RequestContext) -> Response:
        """Ищет питомцев по названиям тегов.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        tags = context.parameters["tags"]
        if not tags:
            raise ApiException(400, "BAD_REQUEST", "At least one tag is required")
        return Responses(self.data.find_pet_by_tags(tags))

    def get_pet_by_id(self, context: RequestContext) -> Response:
        """Возвращает публичную карточку питомца по UUID.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return Responses(self.data.get_pet_by_id(context.identifier("petId")))

    def add_pet(self, context: RequestContext) -> Response:
        """Создаёт питомца только по запросу администратора.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        return Responses(self.data.create_pet(context.validated(PetCreateRequest, V.pet)), status_code=201)

    def update_pet(self, context: RequestContext) -> Response:
        """Обновляет питомца с проверкой текущей версии.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        return Responses(
            self.data.update_pet(context.identifier("petId"), context.validated(PetUpdateRequest, V.pet))
        )

    def delete_pet(self, context: RequestContext) -> Response:
        """Удаляет неиспользуемого питомца только как ADMIN.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        self.data.delete_pet_if_unused(context.identifier("petId"))
        return Response(status_code=204)
