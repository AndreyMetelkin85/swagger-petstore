"""Controllers preserve operation IDs, roles, response codes and service boundaries."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.data.payment_data import PaymentData
from petstore.model.requests import (
    PaymentRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses, public_payment


class PaymentController:
    """Test-card payment creation, replay, history and declined-attempt cleanup."""

    def __init__(self, database: Database) -> None:
        """Configure the payment repository.

        :param database: Application pool.
        """
        self.data = PaymentData(database)

    def create_payment(self, context: RequestContext) -> Response:
        """Create or replay a payment using its required idempotency key.

        :param context: Parent UUID, idempotency header and payment body.
        """
        actor = context.authorize("USER", "ADMIN")
        payment, replayed = self.data.create_payment(
            context.identifier("orderId"),
            context.identifier("Idempotency-Key"),
            context.validated(PaymentRequest, V.payment),
            actor,
        )
        return Responses(public_payment(payment), status_code=200 if replayed else 201)

    def list_payments(self, context: RequestContext) -> Response:
        """Read an authorized order's payment history.

        :param context: Authenticated parent order UUID.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(
            [public_payment(row) for row in self.data.find_payments(context.identifier("orderId"), actor)]
        )

    def get_payment(self, context: RequestContext) -> Response:
        """Read an authorized payment summary.

        :param context: Parent and payment UUIDs with Bearer token.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(
            public_payment(
                self.data.get_payment(context.identifier("orderId"), context.identifier("paymentId"), actor)
            )
        )

    def delete_payment(self, context: RequestContext) -> Response:
        """Delete a declined attempt only as an administrator.

        :param context: Parent and payment UUIDs with ADMIN token.
        """
        context.authorize("ADMIN")
        self.data.delete_declined_payment(context.identifier("orderId"), context.identifier("paymentId"))
        return Response(status_code=204)
