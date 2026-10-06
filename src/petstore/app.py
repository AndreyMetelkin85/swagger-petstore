"""FastAPI transport around the original OpenAPI-first Petstore contract."""

import copy
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from threading import Event, Thread
from typing import Any, cast
from uuid import UUID, uuid4

import yaml
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Message

from petstore.config import Settings
from petstore.controller.admin_user_controller import AdminUserController
from petstore.controller.authentication_controller import AuthenticationController
from petstore.controller.commerce_controller import OPERATIONS, REQUESTS, CommerceController
from petstore.controller.context import RequestContext
from petstore.controller.health_controller import HealthController
from petstore.controller.order_controller import OrderController
from petstore.controller.payment_controller import PaymentController
from petstore.controller.pet_controller import PetController
from petstore.controller.registration_controller import RegistrationController
from petstore.controller.user_controller import UserController
from petstore.data.commerce_order_data import CommerceOrderData
from petstore.data.database import Database, Row
from petstore.data.user_data import UserData
from petstore.model.commerce import CommerceRequest
from petstore.model.requests import (
    AdminUserUpdateRequest,
    LoginRequest,
    OrderCreateRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    PaymentRequest,
    PetCreateRequest,
    PetUpdateRequest,
    RegisterRequest,
    RequestModel,
    UserUpdateRequest,
)
from petstore.service.auth_service import AuthService
from petstore.service.exceptions import ApiException
from petstore.service.media_service import MAX_BYTES
from petstore.utils.responses import Responses

logger = logging.getLogger("petstore")
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger.setLevel(logging.INFO)
Handler = Callable[[RequestContext], Response]
REQUEST_MODELS: dict[str, type[RequestModel]] = {
    "register": RegisterRequest,
    "resendConfirmation": LoginRequest,
    "login": LoginRequest,
    "forgotPassword": PasswordForgotRequest,
    "resetPassword": PasswordResetRequest,
    "updateCurrentUser": UserUpdateRequest,
    "updateUserById": AdminUserUpdateRequest,
    "addPet": PetCreateRequest,
    "updatePet": PetUpdateRequest,
    "createOrderDraft": OrderCreateRequest,
    "updateOrderDraft": OrderCreateRequest,
    "createPayment": PaymentRequest,
}
REQUEST_MODELS.update(REQUESTS)
REQUEST_MODELS["createCommercePayment"] = PaymentRequest


async def upload_body(request: Request) -> tuple[bytes, str, str]:
    """Bound the complete multipart stream before decoding a single image."""
    if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise ApiException(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be multipart/form-data")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BYTES + 65536:
            raise ApiException(413, "IMAGE_TOO_LARGE", "Upload exceeds 10 MiB plus multipart metadata")
        raw.extend(chunk)

    async def receive() -> Message:
        """Provide the already bounded form body to Starlette's parser."""
        return {"type": "http.request", "body": bytes(raw), "more_body": False}

    bounded = Request(request.scope, receive=receive)
    try:
        async with bounded.form(max_files=1, max_fields=2, max_part_size=2048) as form:
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


def resolve(document: Row, value: Row) -> Row:
    """Resolve an internal OpenAPI reference without fetching external resources.

    :param document: Existing contract document.
    :param value: Parameter or operation object.
    """
    if "$ref" not in value:
        return value
    current: Any = document
    for part in value["$ref"].removeprefix("#/").split("/"):
        current = current[part.replace("~1", "/").replace("~0", "~")]
    return cast(Row, current)


def parse_parameters(request: Request, parameters: list[Row], document: Row) -> Row:
    """Adapt UUIDs and required parameters to the existing operation-specific 400 errors.

    :param request: Incoming HTTP request.
    :param parameters: Combined path and operation parameters.
    :param document: Existing OpenAPI contract.
    """
    result: Row = {}
    sources = {
        "path": request.path_params,
        "query": request.query_params,
        "header": request.headers,
        "cookie": request.cookies,
    }
    for raw in parameters:
        parameter = resolve(document, raw)
        name: str = parameter["name"]
        source: str = parameter["in"]
        value = sources[source].get(name)
        if value is None and parameter.get("required"):
            if name == "code":
                code = (
                    "INVALID_RESET_LINK"
                    if "/password/reset" in request.url.path
                    else "INVALID_CONFIRMATION_LINK"
                )
                raise ApiException(400, code, "The one-time link is invalid")
            if name == "Idempotency-Key":
                raise ApiException(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required")
            message = (
                "Status is required"
                if name == "status"
                else "At least one tag is required"
                if name == "tags"
                else "Request parameters are invalid"
            )
            raise ApiException(400, "BAD_REQUEST", message)
        if value is None:
            continue
        schema = resolve(document, parameter.get("schema", {}))
        if schema.get("format") == "uuid":
            try:
                value = UUID(str(value))
            except ValueError as exc:
                if name == "Idempotency-Key":
                    raise ApiException(
                        400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key must be a valid UUID"
                    ) from exc
                label = {"userId": "User", "petId": "Pet", "orderId": "Order", "paymentId": "Payment"}.get(
                    name, "Resource"
                )
                raise ApiException(400, "BAD_REQUEST", f"{label} id must be a valid UUID") from exc
        elif schema.get("type") == "array":
            values = request.query_params.getlist(name) if source == "query" else [str(value)]
            value = [part for item in values for part in item.split(",")]
        result[name] = value
    return result


async def parse_body(request: Request, model: type[RequestModel] | None) -> RequestModel | None:
    """Parse a JSON body while distinguishing absent bytes, malformed JSON and empty objects.

    :param request: Incoming HTTP request.
    :param model: Operation-specific request type, or no request body.
    """
    if model is None:
        return None
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 1024 * 1024:
            raise ApiException(413, "REQUEST_TOO_LARGE", "JSON body exceeds 1 MiB")
        raw.extend(chunk)
    if not raw.strip():
        raise ApiException(400, "BAD_REQUEST", "Request body is required")
    media_type = request.headers.get("Content-Type", "application/json").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise ApiException(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json")
    try:
        value: Any = json.loads(raw, parse_float=Decimal)
        if value is None:
            raise ApiException(400, "BAD_REQUEST", "Request body is required")
        if not isinstance(value, dict):
            raise ValueError("Body must be an object")
        return model.model_validate(value, by_alias=True, by_name=False)
    except ValidationError as exc:
        if issubclass(model, CommerceRequest):
            details = [
                {
                    "field": ".".join(str(part) for part in error["loc"]) or "body",
                    "message": "Invalid field value",
                }
                for error in exc.errors()
            ]
            raise ApiException(422, "VALIDATION_ERROR", "Request validation failed", details) from exc
        raise ApiException(
            400, "BAD_REQUEST", "Request body contains malformed or incompatible JSON"
        ) from exc
    except (ValueError, UnicodeError) as exc:
        raise ApiException(
            400, "BAD_REQUEST", "Request body contains malformed or incompatible JSON"
        ) from exc


def endpoint(
    handler: Handler,
    model: type[RequestModel] | None,
    parameters: list[Row],
    document: Row,
    auth: AuthService,
    multipart: bool = False,
) -> Callable[[Request], Any]:
    """Build a shared transport adapter without duplicating validation in every endpoint.

    :param handler: Original named controller operation.
    :param model: Request model, when the operation has a body.
    :param parameters: Actual OpenAPI parameters.
    :param document: Frozen API contract.
    :param auth: Instance-scoped authentication service.
    """

    async def execute(request: Request) -> Response:
        """Dispatch a parsed request on the worker pool used for synchronous psycopg calls.

        :param request: Incoming HTTP request.
        """
        parsed = parse_parameters(request, parameters, document)
        if multipart:
            await run_in_threadpool(auth.authorize, request.headers.get("Authorization"), "ADMIN")
            upload = await upload_body(request)
            return await run_in_threadpool(handler, RequestContext(request, auth, parsed, None, upload))
        body = await parse_body(request, model)
        return await run_in_threadpool(handler, RequestContext(request, auth, parsed, body))

    return execute


def create_app(
    settings: Settings | None = None, database: Database | None = None, start_database: bool = True
) -> FastAPI:
    """Create an isolated application with the existing API paths and Swagger assets.

    :param settings: Runtime settings; environment values are used when omitted.
    :param database: Injectable PostgreSQL factory for integration and unit tests.
    :param start_database: Disable pool startup only for transport unit tests.
    """
    settings = settings or Settings.from_env()
    database = database or Database(settings)
    db = database
    document: Row = yaml.safe_load((settings.resources / "openapi.yaml").read_text(encoding="utf-8"))
    document = copy.deepcopy(document)
    # Swagger must execute against its own container, not an absolute localhost:8080 from the reference.
    document["servers"][0]["url"] = "/api/v3"
    auth = AuthService(UserData(db), settings)
    stop = Event()

    def expire() -> None:
        """Run a stoppable, row-lock-safe expiry job without logging database values."""
        while not stop.wait(settings.expire_interval):
            try:
                CommerceOrderData(db).expire()
            except Exception as exc:
                logger.error("reservation_expiry_failed type=%s", type(exc).__name__)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        """Manage the pool and background worker for exactly this application instance.

        :param application: FastAPI application entering or leaving its lifespan.
        """
        worker: Thread | None = None
        if start_database:
            await run_in_threadpool(db.start)
            if settings.expire_interval > 0:
                worker = Thread(target=expire, name="petstore-order-expiration", daemon=True)
                worker.start()
        try:
            yield
        finally:
            stop.set()
            if worker:
                await run_in_threadpool(worker.join, 15)
            if start_database:
                await run_in_threadpool(db.close)

    app = FastAPI(
        title=document["info"]["title"],
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        redirect_slashes=False,
    )
    app.state.database = db
    app.state.auth = auth
    app.state.document = document
    app.openapi = lambda: document

    @app.exception_handler(ApiException)
    async def business_error(request: Request, exc: ApiException) -> Response:
        """Render the unchanged business error envelope.

        :param request: Failed request.
        :param exc: Safe public business exception.
        """
        return Responses(
            {"status": exc.status, "error": exc.code, "message": exc.message, "details": exc.details},
            status_code=exc.status,
        )

    @app.exception_handler(HTTPException)
    async def transport_error(request: Request, exc: HTTPException) -> Response:
        """Translate unknown routes and methods into the original error contract.

        :param request: Failed request.
        :param exc: Framework transport exception.
        """
        status = exc.status_code
        if status == 405 and request.url.path.startswith("/api/"):
            known_path = any(
                isinstance(route, APIRoute) and route.path_regex.fullmatch(request.url.path)
                for route in app.routes
            )
            if not known_path:
                status = 404
        code, message = {
            404: ("NOT_FOUND", "The requested endpoint was not found"),
            405: ("METHOD_NOT_ALLOWED", "The HTTP method is not allowed for this endpoint"),
        }.get(status, ("BAD_REQUEST", "Request parameters are invalid"))
        return Responses(
            {"status": status, "error": code, "message": message, "details": []},
            status_code=status,
            headers=exc.headers,
        )

    @app.middleware("http")
    async def safe_log(request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Log method, route and result only, never credentials, bodies or query codes.

        :param request: Incoming request.
        :param call_next: Remaining request pipeline.
        """
        request_id = request.headers.get("X-Request-ID", "")
        if (
            not request_id
            or len(request_id) > 100
            or not all(char.isalnum() or char in "-_." for char in request_id)
        ):
            request_id = str(uuid4())
        started = time.monotonic()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            logger.error("request_failed requestId=%s type=%s", request_id, type(exc).__name__)
            response = Responses(
                {
                    "status": 500,
                    "error": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "details": [],
                },
                status_code=500,
            )
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        template = getattr(route, "path", "unmatched")
        logger.info(
            "request requestId=%s method=%s route=%s status=%s durationMs=%s",
            request_id,
            request.method,
            template,
            response.status_code,
            round((time.monotonic() - started) * 1000),
        )
        return response

    controllers = [
        HealthController(db),
        RegistrationController(),
        AuthenticationController(),
        PetController(db),
        OrderController(db),
        PaymentController(db),
        UserController(),
        AdminUserController(),
    ]
    commerce = CommerceController(db, settings)
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "delete", "patch", "head", "options"}:
                continue
            operation_id: str = operation["operationId"]
            handlers = [
                getattr(controller, operation_id)
                for controller in controllers
                if hasattr(controller, operation_id)
            ]
            if operation_id in OPERATIONS:
                handlers.append(commerce.handler(operation_id))
            if len(handlers) != 1:
                raise RuntimeError(f"Operation {operation_id} must have exactly one controller")
            if (
                "requestBody" in operation
                and operation_id not in REQUEST_MODELS
                and operation_id != "uploadMedia"
            ):
                raise RuntimeError(f"Operation {operation_id} is missing its request model")
            parameters = path_item.get("parameters", []) + operation.get("parameters", [])
            app.add_api_route(
                "/api/v3" + path,
                endpoint(
                    cast(Handler, handlers[0]),
                    REQUEST_MODELS.get(operation_id),
                    parameters,
                    document,
                    auth,
                    operation_id == "uploadMedia",
                ),
                methods=[method.upper()],
                name=operation_id,
                operation_id=operation_id,
                include_in_schema=False,
            )

    @app.get("/api/v3/openapi.json", include_in_schema=False)
    def openapi_json() -> Response:
        """Serve the existing contract rather than an incompatible generated replacement."""
        return Responses(document)

    @app.get("/api/v3/openapi.yaml", include_in_schema=False)
    def openapi_yaml() -> Response:
        """Serve a YAML representation of the same contract."""
        return Response(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False), media_type="application/yaml"
        )

    app.mount("/", StaticFiles(directory=str(settings.static), html=True), name="swagger-ui")
    return app


app = create_app()
