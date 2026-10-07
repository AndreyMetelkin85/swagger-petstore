"""Owned, versioned cart HTTP handlers."""

from typing import cast
from uuid import UUID

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.model.commerce import CartCommand
from petstore.service.cart_service import CartService
from petstore.utils.responses import Responses


class CartController:
    """Keep authentication separate from cart availability and replay rules."""

    def __init__(self, database: Database) -> None:
        """Inject the application cart repository."""
        self.cart = CartService(database)

    def get(self, context: RequestContext) -> Response:
        """Read only the authenticated account's cart."""
        return Responses(self.cart.get(context.authorize("USER", "ADMIN")))

    def replace(self, context: RequestContext) -> Response:
        """Replace an owned cart using its version and optional replay token."""
        assert isinstance(context.body, CartCommand)
        return Responses(
            self.cart.replace(
                context.body,
                context.authorize("USER", "ADMIN"),
                cast(UUID | None, context.parameters.get("Idempotency-Key")),
            )
        )
