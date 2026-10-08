"""FastAPI transport around the original OpenAPI-first Petstore contract."""

import copy
import logging
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from threading import Event, Thread
from typing import Any
from uuid import uuid4

import yaml
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute, iter_route_contexts
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from petstore.api.dependencies import validation_error
from petstore.api.registry import Controllers, include_routers
from petstore.config import Settings
from petstore.data.database import Database, Row
from petstore.data.user_data import UserData
from petstore.model.responses import ErrorResponse
from petstore.service.auth_service import AuthService
from petstore.service.commerce_order_service import CommerceOrderService
from petstore.service.demo_catalog_service import populate_demo_catalog
from petstore.service.exceptions import ApiException
from petstore.service.media_service import MediaService
from petstore.utils.responses import Responses

logger = logging.getLogger("petstore")


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
        next_media_cleanup = 0.0
        while not stop.wait(settings.expire_interval):
            try:
                CommerceOrderService(db).expire()
                if time.monotonic() >= next_media_cleanup:
                    MediaService(db, settings).cleanup()
                    next_media_cleanup = time.monotonic() + 3600
            except Exception as exc:
                logger.error("reservation_expiry_failed type=%s", type(exc).__name__)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        """Manage the pool and background worker for exactly this application instance.

        :param application: FastAPI application entering or leaving its lifespan.
        """
        worker: Thread | None = None
        logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        logger.setLevel(logging.INFO)
        if start_database:
            await run_in_threadpool(db.start)
            if settings.demo_catalog:
                try:
                    await run_in_threadpool(populate_demo_catalog, db, settings)
                except Exception:
                    await run_in_threadpool(db.close)
                    raise
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
        payload = ErrorResponse.model_validate(
            {"status": exc.status, "error": exc.code, "message": exc.message, "details": exc.details}
        )
        return Responses(
            payload.model_dump(),
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, exc: RequestValidationError) -> Response:
        """Preserve documented errors without exposing Pydantic inputs or security values."""
        return await business_error(request, validation_error(request, exc))

    @app.exception_handler(HTTPException)
    async def transport_error(request: Request, exc: HTTPException) -> Response:
        """Translate unknown routes and methods into the original error contract.

        :param request: Failed request.
        :param exc: Framework transport exception.
        """
        status = exc.status_code
        if status == 405 and request.url.path.startswith("/api/"):
            known_path = any(
                isinstance(route.original_route, APIRoute) and route.path_regex.fullmatch(request.url.path)
                for route in iter_route_contexts(app.routes)
            )
            if not known_path:
                status = 404
        code, message = {
            404: ("NOT_FOUND", "The requested endpoint was not found"),
            405: ("METHOD_NOT_ALLOWED", "The HTTP method is not allowed for this endpoint"),
        }.get(status, ("BAD_REQUEST", "Request parameters are invalid"))
        payload = ErrorResponse(status=status, error=code, message=message, details=[])
        return Responses(
            payload.model_dump(),
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

    app.state.controllers = Controllers.create(db, settings)
    include_routers(app)

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
