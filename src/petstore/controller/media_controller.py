"""Авторизация и передача HTTP-команд сервисам приложения."""

from starlette.responses import Response

from petstore.config import Settings
from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.service.media_service import MediaService
from petstore.utils.responses import Responses


class MediaController:
    """Проверка доступа и передача ограниченных загрузок медиасервису."""

    def __init__(self, database: Database, settings: Settings) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :param settings: Настройки приложения и его инфраструктурных подключений.
        :return: Ничего не возвращает.
        """
        self.media = MediaService(database, settings)

    def upload(self, context: RequestContext) -> Response:
        """Принимает проверенную загрузку ADMIN; имя файла не используется как путь хранения.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("ADMIN")
        assert context.upload is not None
        return Responses(self.media.upload(*context.upload, actor), status_code=201)

    def get(self, context: RequestContext, thumbnail: bool | None = None) -> Response:
        """Возвращает метаданные или содержимое изображения после проверки видимости.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :param thumbnail: Запросить миниатюру вместо полного изображения.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("USER", "ADMIN") if context.request.headers.get("Authorization") else None
        result = self.media.get(context.identifier("id"), actor, thumbnail)
        if isinstance(result, tuple):
            return Response(
                result[0],
                media_type=result[1],
                headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"},
            )
        return Responses(result)

    def delete(self, context: RequestContext) -> Response:
        """Удаляет неиспользуемое изображение как ADMIN, сохраняя обложки заказов.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        self.media.delete(context.identifier("id"))
        return Response(status_code=204)
