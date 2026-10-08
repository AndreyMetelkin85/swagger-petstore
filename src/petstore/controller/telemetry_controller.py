"""Авторизация и передача HTTP-команд сервисам приложения."""

import logging
import re
import time
from collections.abc import Callable
from threading import Lock
from typing import cast

import yaml
from starlette.responses import Response

from petstore.config import Settings
from petstore.controller.context import RequestContext
from petstore.data.database import Row
from petstore.model.commerce import TelemetryCommand
from petstore.service.exceptions import ApiException

logger = logging.getLogger("petstore.telemetry")


class TelemetryController:
    """Ограничение телеметрии в рамках экземпляра приложения, без глобального состояния."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, settings: Settings | None = None) -> None:
        """Создаёт потокобезопасное окно ограничения до 100 пачек событий в минуту.

        :param clock: Источник времени для ограничения запросов и управляемых тестов.
        :param settings: Настройки приложения и его инфраструктурных подключений.
        :return: Ничего не возвращает.
        """
        self.clock = clock
        settings = settings or Settings.from_env()
        document = yaml.safe_load((settings.resources / "openapi.yaml").read_text(encoding="utf-8"))
        self.endpoints = {re.sub(r"\{[^}]+\}", ":id", path) for path in document["paths"]}
        self.routes = {
            "/",
            "/catalog",
            "/pets",
            "/cart",
            "/checkout",
            "/login",
            "/register",
            "/forgot-password",
            "/reset-password",
            "/confirm/:id",
            "/account",
            "/account/profile",
            "/account/orders",
            "/account/orders/:id",
            "/products/:id",
            "/pets/:id",
            "/admin",
            "/admin/products",
            "/admin/products/new",
            "/admin/products/:id",
            "/admin/pets",
            "/admin/pets/new",
            "/admin/pets/:id",
            "/admin/orders",
            "/admin/orders/:id",
            "/admin/users",
            "/admin/categories",
        }
        self.errors = {
            "UNEXPECTED",
            "SERVICE_UNAVAILABLE",
            "API_CONTRACT_MISMATCH",
            "DRAFT_STATUS_UNKNOWN",
            "PLACE_STATUS_UNKNOWN",
            "PAYMENT_STATUS_UNKNOWN",
            "STARTUP_FAILED",
            "STORAGE_UNAVAILABLE",
        }
        self.routes.update(
            {"/about", "/catalog/:id", "/register/verify", "/register/complete", "/admin/logs"}
        )
        for item in document["paths"].values():
            for raw_operation in item.values():
                if not isinstance(raw_operation, dict):
                    continue
                operation = cast(Row, raw_operation)
                for response in operation.get("responses", {}).values():
                    for example in (
                        response.get("content", {}).get("application/json", {}).get("examples", {}).values()
                    ):
                        code = example.get("value", {}).get("error")
                        if isinstance(code, str):
                            self.errors.add(code)
        self.lock = Lock()
        self.window = 0.0
        self.count = 0

    def client_events(self, context: RequestContext) -> Response:
        """Принимает только разрешённые события и безопасные числовые или перечислимые метаданные.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        command = context.body
        assert isinstance(command, TelemetryCommand)
        allowed = {
            "api_result",
            "api_failure",
            "client_error",
            "cart_merge",
            "checkout",
            "media_upload",
            "navigation",
        }
        if any(event.event not in allowed for event in command.events):
            raise ApiException(422, "VALIDATION_ERROR", "Unknown telemetry event")
        for event in command.events:
            if (
                (event.error_code is not None and event.error_code not in self.errors)
                or (event.endpoint_template is not None and event.endpoint_template not in self.endpoints)
                or (event.route_id is not None and event.route_id not in self.routes)
            ):
                raise ApiException(422, "VALIDATION_ERROR", "Unsupported telemetry metadata")
        actor = context.authorize("USER", "ADMIN") if context.request.headers.get("Authorization") else None
        with self.lock:
            now = self.clock()
            if now - self.window >= 60:
                self.window, self.count = now, 0
            if self.count >= 100:
                raise ApiException(429, "TELEMETRY_RATE_LIMITED", "Too many telemetry batches")
            self.count += 1
        logger.info("client_events count=%s", len(command.events))
        for event in command.events:
            logger.info(
                "client_event event=%s method=%s httpStatus=%s durationMs=%s requestId=%s errorCode=%s resourceId=%s routeId=%s endpointTemplate=%s timestamp=%s actorId=%s",
                event.event,
                event.method,
                event.http_status,
                event.duration_ms,
                event.request_id,
                event.error_code,
                event.resource_id,
                event.route_id,
                event.endpoint_template,
                event.timestamp.isoformat() if event.timestamp is not None else None,
                actor["id"] if actor else None,
            )
        return Response(status_code=204)
