"""HTTP-маршруты, зависимости FastAPI и публичные DTO."""

import json
from collections.abc import Callable, Coroutine
from decimal import Decimal
from typing import Annotated, Any, cast

from fastapi import Depends
from fastapi.dependencies.utils import request_params_to_args
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Message

from petstore.controller.context import RequestContext
from petstore.model.commerce import CommerceRequest
from petstore.service.auth_service import AuthService
from petstore.service.exceptions import ApiException
from petstore.service.media_service import MAX_BYTES


class DecimalRequest(Request):
    """Разбор денежных JSON-чисел как Decimal перед валидацией Pydantic."""

    async def json(self) -> Any:
        """Разбирает ограниченное JSON-тело с точными Decimal вместо float.

        :return: Результат операции типа Any.
        """
        if not hasattr(self, "_json"):
            self._json = json.loads(await self.body(), parse_float=Decimal)
        return self._json

    def cache_body(self, content: bytes) -> None:
        """Сохраняет ограниченный поток для последующего чтения Body в FastAPI.

        :param content: Данные для сериализации в публичный ответ.
        :return: Ничего не возвращает.
        """
        self._body = content


class ContractRoute(APIRoute):
    """Маршрут FastAPI с ограничением тела и совместимыми транспортными ошибками."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Ограничивает JSON-тело перед стандартной проверкой модели FastAPI.

        :return: Результат операции типа Callable[[Request], Coroutine[Any, Any, Response]].
        """
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            """Различает пустое или повреждённое тело и ошибки отдельных полей.

            :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
            :return: HTTP-ответ с публичными данными и статусом операции.
            """
            request = DecimalRequest(request.scope, request.receive)
            if self.body_field is not None:
                # Проверяем поля FastAPI: ошибки параметров по контракту предшествуют ошибкам тела.
                for fields, values in (
                    (self.dependant.path_params, request.path_params),
                    (self.dependant.query_params, request.query_params),
                    (self.dependant.header_params, request.headers),
                ):
                    _, errors = request_params_to_args(fields, values)
                    if errors:
                        raise RequestValidationError(errors)
                raw = bytearray()
                async for chunk in request.stream():
                    if len(raw) + len(chunk) > 1024 * 1024:
                        raise ApiException(413, "REQUEST_TOO_LARGE", "JSON body exceeds 1 MiB")
                    raw.extend(chunk)
                request.cache_body(bytes(raw))
                if not raw.strip():
                    raise ApiException(400, "BAD_REQUEST", "Request body is required")
                media_type = (
                    request.headers.get("Content-Type", "application/json").split(";", 1)[0].strip().lower()
                )
                if media_type != "application/json":
                    raise ApiException(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json")
                try:
                    value = await request.json()
                    if value is None:
                        raise ApiException(400, "BAD_REQUEST", "Request body is required")
                    if not isinstance(value, dict):
                        raise ValueError("Body must be an object")
                except (ValueError, UnicodeError) as exc:
                    raise ApiException(
                        400, "BAD_REQUEST", "Request body contains malformed or incompatible JSON"
                    ) from exc
            return await original(request)

        return handle


def request_context(request: Request) -> RequestContext:
    """Создаёт контекст с сервисом авторизации приложения; HTTP-валидацию выполняет FastAPI.

    :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
    :return: Результат операции типа RequestContext.
    """
    return RequestContext(request, cast(AuthService, request.app.state.auth), {}, None)


Context = Annotated[RequestContext, Depends(request_context)]


def decode_response(result: Response, response: Response) -> Any:
    """Переносит HTTP-статус контроллера и разбирает JSON перед проверкой модели ответа FastAPI.

    Входной result уже содержит публичный JSON, а не приватную строку базы.
    Числа разбираются как Decimal. Возвращаемые данные проверяются response_model маршрута.

    :param result: Публичный JSON-ответ контроллера; не приватная строка базы.
    :param response: Ответ FastAPI, в который переносится HTTP-статус результата контроллера.
    :return: Результат операции типа Any.
    """
    response.status_code = result.status_code
    return json.loads(bytes(result.body), parse_float=Decimal)


def validation_error(request: Request, exc: RequestValidationError) -> ApiException:
    """Преобразует ошибки FastAPI в безопасные публичные ошибки соответствующей операции.

    :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
    :param exc: Обрабатываемое исключение.
    :return: Результат операции типа ApiException.
    """
    errors = exc.errors()
    # Сохраняем приоритет ошибок параметров без вывода исходных значений.
    for error in errors:
        location = error["loc"]
        if not location or location[0] == "body":
            continue
        name = str(location[-1])
        if name == "code" and error["type"] == "missing":
            code = (
                "INVALID_RESET_LINK" if "/password/reset" in request.url.path else "INVALID_CONFIRMATION_LINK"
            )
            return ApiException(400, code, "The one-time link is invalid")
        if name == "Idempotency-Key":
            if error["type"] == "missing":
                return ApiException(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required")
            return ApiException(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key must be a valid UUID")
        if error["type"] in {"uuid_parsing", "uuid_type"}:
            label = {"userId": "User", "petId": "Pet", "orderId": "Order", "paymentId": "Payment"}.get(
                name, "Resource"
            )
            return ApiException(400, "BAD_REQUEST", f"{label} id must be a valid UUID")
        if error["type"] == "missing":
            message = (
                "Status is required"
                if name == "status"
                else "At least one tag is required"
                if name == "tags"
                else "Request parameters are invalid"
            )
            return ApiException(400, "BAD_REQUEST", message)
    route = request.scope.get("route")
    commerce = getattr(route, "tags", []) == ["commerce"]
    if any(error["loc"][0] == "body" for error in errors):
        field = getattr(route, "body_field", None)
        model = field.field_info.annotation if field is not None else None
        commerce = isinstance(model, type) and issubclass(model, CommerceRequest)
    if commerce:
        details = [
            {
                "field": (".".join(str(part) for part in error["loc"][1:]) or "body")[:100],
                "message": "Invalid field value",
            }
            for error in errors[:100]
        ]
        return ApiException(422, "VALIDATION_ERROR", "Request validation failed", details)
    return ApiException(400, "BAD_REQUEST", "Request body contains malformed or incompatible JSON")


async def upload_body(request: Request) -> tuple[bytes, str, str]:
    """Ограничивает весь multipart-поток перед декодированием одного изображения.

    :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
    :return: Результат операции типа tuple[bytes, str, str].
    """
    if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise ApiException(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be multipart/form-data")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BYTES + 65536:
            raise ApiException(413, "IMAGE_TOO_LARGE", "Upload exceeds 10 MiB plus multipart metadata")
        raw.extend(chunk)

    async def receive() -> Message:
        """Предоставляет сохранённое ограниченное тело multipart-парсеру Starlette.

        :return: Результат операции типа Message.
        """
        return {"type": "http.request", "body": bytes(raw), "more_body": False}

    bounded = Request(request.scope, receive=receive)
    try:
        async with bounded.form(max_files=1, max_fields=2, max_part_size=4096) as form:
            if set(form.keys()) - {"file", "sourceType", "sourceNote"}:
                raise ApiException(422, "VALIDATION_ERROR", "Unknown upload fields")
            if len(form.multi_items()) != len(form):
                raise ApiException(422, "VALIDATION_ERROR", "Upload fields must not be repeated")
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise ApiException(422, "INVALID_IMAGE", "A single file is required")
            payload = await file.read(MAX_BYTES + 1)
            source_type, source_note = form.get("sourceType", "OWN"), form.get("sourceNote", "")
            if not isinstance(source_type, str) or not isinstance(source_note, str):
                raise ApiException(422, "VALIDATION_ERROR", "Invalid source metadata")
            return payload, source_type, source_note
    except HTTPException as exc:
        raise ApiException(422, "INVALID_IMAGE", "Multipart form is invalid") from exc


async def upload_context(context: Context) -> RequestContext:
    """Проверяет роль ADMIN до чтения и декодирования ограниченной загрузки.

    :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
    :return: Результат операции типа RequestContext.
    """
    await run_in_threadpool(context.auth.authorize, context.request.headers.get("Authorization"), "ADMIN")
    context.upload = await upload_body(context.request)
    return context


UploadContext = Annotated[RequestContext, Depends(upload_context)]
