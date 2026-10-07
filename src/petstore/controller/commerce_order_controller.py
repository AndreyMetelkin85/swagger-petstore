"""Mixed checkout and payment HTTP handlers; transaction rules belong to services."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.data.payment_data import PaymentData
from petstore.model.commerce import CheckoutCommand, VersionCommand
from petstore.model.enums import OrderStatus
from petstore.model.requests import PaymentRequest
from petstore.service.commerce_order_service import CommerceOrderService
from petstore.service.validation_service import ValidationService
from petstore.utils.responses import Responses, public_payment


class CommerceOrderController:
    """Adapt authenticated mixed-order commands to a single transaction service."""

    def __init__(self, database: Database) -> None:
        """Share the application pool with legacy order and payment operations."""
        self.orders = CommerceOrderService(database)
        self.payments = PaymentData(database)

    def list_orders(self, context: RequestContext) -> Response:
        """List owned orders, or the entire history for ADMIN."""
        return Responses(self.orders.find_all(context.authorize("USER", "ADMIN")))

    def create(self, context: RequestContext) -> Response:
        """Snapshot a cart draft, returning 200 for a safely replayed creation."""
        assert isinstance(context.body, CheckoutCommand)
        result, replayed = self.orders.create(
            context.body, context.authorize("USER", "ADMIN"), context.identifier("Idempotency-Key")
        )
        return Responses(result, status_code=200 if replayed else 201)

    def get(self, context: RequestContext) -> Response:
        """Read an order after access checks and overdue-reservation reconciliation."""
        return Responses(self.orders.get(context.identifier("id"), context.authorize("USER", "ADMIN")))

    def delete(self, context: RequestContext) -> Response:
        """Atomically delete a permitted order and its dependent payments."""
        self.orders.delete(context.identifier("id"), context.authorize("USER", "ADMIN"))
        return Response(status_code=204)

    def place(self, context: RequestContext) -> Response:
        """Validate and reserve the entire draft composition atomically."""
        assert isinstance(context.body, VersionCommand)
        return Responses(
            self.orders.place(
                context.identifier("id"),
                context.authorize("USER", "ADMIN"),
                context.body.version,
                context.identifier("Idempotency-Key"),
            )
        )

    def transition(self, context: RequestContext, target: OrderStatus) -> Response:
        """Apply authorized lifecycle rules; cancellation permits the owning USER."""
        actor = context.authorize("USER", "ADMIN")
        if target != OrderStatus.CANCELLED:
            context.authorize("ADMIN")
        assert isinstance(context.body, VersionCommand)
        return Responses(
            self.orders.transition(context.identifier("id"), target, actor, context.body.version)
        )

    def list_payments(self, context: RequestContext) -> Response:
        """Expose safe payment summaries for an accessible order."""
        return Responses(
            [
                public_payment(row)
                for row in self.payments.find_payments(
                    context.identifier("id"), context.authorize("USER", "ADMIN")
                )
            ]
        )

    def create_payment(self, context: RequestContext) -> Response:
        """Use the existing simulator and the same order lock as checkout/expiry."""
        actor = context.authorize("USER", "ADMIN")
        request = context.validated(PaymentRequest, ValidationService.payment)
        result, replayed = self.payments.create_payment(
            context.identifier("id"), context.identifier("Idempotency-Key"), request, actor
        )
        return Responses(public_payment(result), status_code=200 if replayed else 201)
