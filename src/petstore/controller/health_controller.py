"""Авторизация и передача HTTP-команд сервисам приложения."""

from datetime import UTC, datetime

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.utils.responses import Responses


class HealthController:
    """Публичная проверка готовности API и PostgreSQL."""

    def __init__(self, database: Database) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.database = database

    def health(self, context: RequestContext) -> Response:
        """Возвращает готовность API и PostgreSQL в действующем формате.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        healthy = self.database.is_healthy()
        state = "UP" if healthy else "DOWN"
        return Responses(
            {
                "status": state,
                "service": "swagger-petstore",
                "database": state,
                "timestamp": datetime.now(UTC),
            },
            status_code=200 if healthy else 503,
        )
