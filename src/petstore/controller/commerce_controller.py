"""OpenAPI operation registry for catalog, media, cart and mixed checkout."""

import logging
import time
from collections.abc import Callable
from functools import partial
from threading import Lock
from typing import cast
from uuid import UUID

from starlette.responses import Response

from petstore.config import Settings
from petstore.controller.context import RequestContext
from petstore.data.cart_data import CartData
from petstore.data.catalog_data import CatalogData
from petstore.data.commerce_order_data import CommerceOrderData
from petstore.data.database import Database
from petstore.data.payment_data import PaymentData
from petstore.model.commerce import (
    CartCommand,
    CategoryCommand,
    CheckoutCommand,
    CommerceRequest,
    PetCardCommand,
    ProductCommand,
    StockCommand,
    TelemetryCommand,
    VersionCommand,
)
from petstore.model.enums import OrderStatus
from petstore.model.requests import PaymentRequest
from petstore.service.exceptions import ApiException
from petstore.service.media_service import MediaService
from petstore.service.validation_service import ValidationService
from petstore.utils.responses import Responses, public_payment

logger = logging.getLogger("petstore.telemetry")

# Registry entries describe a domain operation, not a second implementation per endpoint.
OPERATIONS: dict[str, tuple[str, str, str]] = {
    "listProducts": ("list", "product", "public"),
    "getProduct": ("get", "product", "public"),
    "listAdminProducts": ("list", "product", "admin"),
    "getAdminProduct": ("get", "product", "admin"),
    "createProduct": ("save", "product", "create"),
    "updateProduct": ("save", "product", "update"),
    "publishProduct": ("publish", "product", "PUBLISHED"),
    "unpublishProduct": ("publish", "product", "DRAFT"),
    "archiveProduct": ("publish", "product", "ARCHIVED"),
    "adjustProductStock": ("stock", "product", ""),
    "listCategories": ("categories", "", "public"),
    "listAdminCategories": ("categories", "", "admin"),
    "createCategory": ("category", "", "create"),
    "updateCategory": ("category", "", "update"),
    "listCatalogPets": ("list", "pet", "public"),
    "getCatalogPet": ("get", "pet", "public"),
    "listAdminPets": ("list", "pet", "admin"),
    "getAdminPet": ("get", "pet", "admin"),
    "createPetCard": ("save", "pet", "create"),
    "updatePetCard": ("save", "pet", "update"),
    "publishPetCard": ("publish", "pet", "PUBLISHED"),
    "unpublishPetCard": ("publish", "pet", "DRAFT"),
    "archivePetCard": ("publish", "pet", "ARCHIVED"),
    "uploadMedia": ("media", "", "upload"),
    "getMedia": ("media", "", "metadata"),
    "getMediaImage": ("media", "", "image"),
    "getMediaThumb": ("media", "", "thumb"),
    "deleteMedia": ("media", "", "delete"),
    "getCart": ("cart", "", "get"),
    "replaceCart": ("cart", "", "put"),
    "listCommerceOrders": ("orders", "", "list"),
    "createCommerceOrder": ("orders", "", "create"),
    "getCommerceOrder": ("orders", "", "get"),
    "deleteCommerceOrder": ("orders", "", "delete"),
    "placeCommerceOrder": ("orders", "", "place"),
    "approveCommerceOrder": ("orders", "", "approved"),
    "shipCommerceOrder": ("orders", "", "shipped"),
    "deliverCommerceOrder": ("orders", "", "delivered"),
    "cancelCommerceOrder": ("orders", "", "cancelled"),
    "listCommercePayments": ("payments", "", "list"),
    "createCommercePayment": ("payments", "", "create"),
    "clientEvents": ("telemetry", "", ""),
}

REQUESTS: dict[str, type[CommerceRequest]] = {
    **{operation: ProductCommand for operation in ("createProduct", "updateProduct")},
    **{operation: PetCardCommand for operation in ("createPetCard", "updatePetCard")},
    **{operation: CategoryCommand for operation in ("createCategory", "updateCategory")},
    **{
        operation: VersionCommand
        for operation in (
            "publishProduct",
            "unpublishProduct",
            "archiveProduct",
            "publishPetCard",
            "unpublishPetCard",
            "archivePetCard",
            "placeCommerceOrder",
            "approveCommerceOrder",
            "shipCommerceOrder",
            "deliverCommerceOrder",
            "cancelCommerceOrder",
        )
    },
    "adjustProductStock": StockCommand,
    "replaceCart": CartCommand,
    "createCommerceOrder": CheckoutCommand,
    "clientEvents": TelemetryCommand,
}


def body[Command: CommerceRequest](context: RequestContext, model: type[Command]) -> Command:
    """Return a command already validated by the shared transport."""
    assert isinstance(context.body, model)
    return context.body


def key(context: RequestContext) -> UUID | None:
    """Read the transport-validated optional/required idempotency header."""
    return cast(UUID | None, context.parameters.get("Idempotency-Key"))


class CommerceController:
    """Bind explicit operations to shared domain handlers without CRUD duplication."""

    def __init__(self, database: Database, settings: Settings) -> None:
        """Configure domain repositories and bounded telemetry state."""
        self.catalog = CatalogData(database)
        self.cart = CartData(database)
        self.orders = CommerceOrderData(database)
        self.payments = PaymentData(database)
        self.media = MediaService(database, settings)
        self.telemetry_lock = Lock()
        self.telemetry_window = 0.0
        self.telemetry_count = 0

    def handler(self, operation: str) -> Callable[[RequestContext], Response]:
        """Return exactly one named handler for an OpenAPI operation."""
        return partial(self.dispatch, operation)

    def dispatch(self, operation: str, context: RequestContext) -> Response:
        """Authorize and execute the registry's catalog/store/media operation."""
        domain, kind, action = OPERATIONS[operation]
        identifier = context.identifier("id") if "id" in context.parameters else None
        if domain in {"list", "get", "categories"}:
            public = action == "public"
            if not public:
                context.authorize("ADMIN")
            if domain == "list":
                return Responses(self.catalog.find_all(kind, public, dict(context.request.query_params)))
            if domain == "get":
                assert identifier is not None
                return Responses(self.catalog.get(kind, identifier, public))
            return Responses(self.catalog.categories(public, context.request.query_params.get("kind")))
        if domain in {"save", "publish", "stock", "category"}:
            actor = context.authorize("ADMIN")
            if domain == "save":
                command = (
                    body(context, ProductCommand) if kind == "product" else body(context, PetCardCommand)
                )
                return Responses(
                    self.catalog.save(command, identifier), status_code=201 if action == "create" else 200
                )
            if domain == "publish":
                assert identifier is not None
                return Responses(
                    self.catalog.publish(kind, identifier, body(context, VersionCommand).version, action)
                )
            if domain == "stock":
                assert identifier is not None
                return Responses(self.catalog.adjust_stock(identifier, body(context, StockCommand), actor))
            return Responses(
                self.catalog.save_category(body(context, CategoryCommand), identifier),
                status_code=201 if action == "create" else 200,
            )
        if domain == "media":
            if action == "upload":
                actor = context.authorize("ADMIN")
                assert context.upload is not None
                payload, source_type, source_note = context.upload
                return Responses(self.media.upload(payload, source_type, source_note, actor), status_code=201)
            assert identifier is not None
            if action == "delete":
                context.authorize("ADMIN")
                self.media.delete(identifier)
                return Response(status_code=204)
            actor = (
                context.authorize("USER", "ADMIN") if context.request.headers.get("Authorization") else None
            )
            result = self.media.get(identifier, actor, None if action == "metadata" else action == "thumb")
            if isinstance(result, tuple):
                return Response(
                    result[0],
                    media_type=result[1],
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"},
                )
            return Responses(result)
        if domain == "telemetry":
            command = body(context, TelemetryCommand)
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
            with self.telemetry_lock:
                now = time.monotonic()
                if now - self.telemetry_window >= 60:
                    self.telemetry_window, self.telemetry_count = now, 0
                if self.telemetry_count >= 100:
                    raise ApiException(429, "TELEMETRY_RATE_LIMITED", "Too many telemetry batches")
                self.telemetry_count += 1
            logger.info("client_events count=%s", len(command.events))
            for event in command.events:
                logger.info(
                    "client_event event=%s method=%s httpStatus=%s durationMs=%s",
                    event.event,
                    event.method,
                    event.http_status,
                    event.duration_ms,
                )
            return Response(status_code=204)
        actor = context.authorize("USER", "ADMIN")
        if domain == "cart":
            return Responses(
                self.cart.get(actor)
                if action == "get"
                else self.cart.replace(body(context, CartCommand), actor, key(context))
            )
        if domain == "payments":
            assert identifier is not None
            if action == "list":
                return Responses(
                    [public_payment(row) for row in self.payments.find_payments(identifier, actor)]
                )
            request = context.validated(PaymentRequest, ValidationService.payment)
            token = key(context)
            assert token is not None
            result, replayed = self.payments.create_payment(identifier, token, request, actor)
            return Responses(public_payment(result), status_code=200 if replayed else 201)
        if action == "list":
            return Responses(self.orders.find_all(actor))
        if action == "create":
            token = key(context)
            assert token is not None
            result, replayed = self.orders.create(body(context, CheckoutCommand), actor, token)
            return Responses(result, status_code=200 if replayed else 201)
        assert identifier is not None
        if action == "get":
            return Responses(self.orders.get(identifier, actor))
        if action == "delete":
            self.orders.delete(identifier, actor)
            return Response(status_code=204)
        version = body(context, VersionCommand).version
        if action == "place":
            token = key(context)
            assert token is not None
            return Responses(self.orders.place(identifier, actor, version, token))
        if action != "cancelled":
            context.authorize("ADMIN")
        return Responses(self.orders.transition(identifier, OrderStatus(action), actor, version))
