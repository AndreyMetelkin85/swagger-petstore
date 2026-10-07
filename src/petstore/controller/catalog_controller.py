"""Catalog HTTP authorization and command adaptation, without operation-name dispatch."""

from uuid import UUID

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.model.commerce import (
    CategoryCommand,
    PetCardCommand,
    ProductCommand,
    StockCommand,
    VersionCommand,
)
from petstore.service.catalog_service import CatalogService
from petstore.utils.responses import Responses


class CatalogController:
    """Product, pet and category handlers sharing the same catalog rules."""

    def __init__(self, database: Database) -> None:
        """Inject the application's catalog repository."""
        self.catalog = CatalogService(database)

    def list_cards(self, context: RequestContext, kind: str, public: bool) -> Response:
        """List public cards or require ADMIN for unpublished cards."""
        if not public:
            context.authorize("ADMIN")
        return Responses(self.catalog.find_all(kind, public, dict(context.request.query_params)))

    def get_card(self, context: RequestContext, kind: str, public: bool) -> Response:
        """Read one visible card, checking the administrator role when needed."""
        if not public:
            context.authorize("ADMIN")
        return Responses(self.catalog.get(kind, context.identifier("id"), public))

    def save_card(self, context: RequestContext, kind: str, identifier: UUID | None) -> Response:
        """Create or fully replace an administrator-owned catalog command."""
        context.authorize("ADMIN")
        command = context.body
        assert isinstance(command, (ProductCommand, PetCardCommand))
        return Responses(
            self.catalog.save(command, identifier), status_code=201 if identifier is None else 200
        )

    def publish(self, context: RequestContext, kind: str, target: str) -> Response:
        """Apply a versioned publication action as ADMIN."""
        context.authorize("ADMIN")
        assert isinstance(context.body, VersionCommand)
        return Responses(self.catalog.publish(kind, context.identifier("id"), context.body.version, target))

    def adjust_stock(self, context: RequestContext) -> Response:
        """Apply and audit an ADMIN inventory delta under the product lock."""
        actor = context.authorize("ADMIN")
        assert isinstance(context.body, StockCommand)
        return Responses(self.catalog.adjust_stock(context.identifier("id"), context.body, actor))

    def categories(self, context: RequestContext, public: bool) -> Response:
        """List categories without removing inactive categories' existing cards."""
        if not public:
            context.authorize("ADMIN")
        return Responses(self.catalog.categories(public, context.request.query_params.get("kind")))

    def save_category(self, context: RequestContext, identifier: UUID | None) -> Response:
        """Create or version-update a category as ADMIN."""
        context.authorize("ADMIN")
        assert isinstance(context.body, CategoryCommand)
        return Responses(
            self.catalog.save_category(context.body, identifier),
            status_code=201 if identifier is None else 200,
        )
