"""Controllers preserve operation IDs, roles, response codes and service boundaries."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.data.order_data import OrderData
from petstore.model.enums import OrderStatus
from petstore.model.requests import (
    OrderCreateRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses, public_order


class OrderController:
    """Drafts, checkout, lifecycle actions and role-aware deletion."""

    def __init__(self, database: Database) -> None:
        """Configure the order repository.

        :param database: Application pool.
        """
        self.data = OrderData(database)

    def getInventory(self, context: RequestContext) -> Response:
        """Read order inventory totals only as an administrator.

        :param context: Administrator request.
        """
        context.authorize("ADMIN")
        return Responses(self.data.get_count_by_status())

    def listOrders(self, context: RequestContext) -> Response:
        """List all orders for administrators or only the caller's orders.

        :param context: Authenticated list request.
        """
        return Responses(
            [public_order(row) for row in self.data.find_all(context.authorize("USER", "ADMIN"))]
        )

    def getOrderById(self, context: RequestContext) -> Response:
        """Read an order after checking ownership.

        :param context: Authenticated order UUID.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(public_order(self.data.get_order_by_id(context.identifier("orderId"), actor)))

    def createOrderDraft(self, context: RequestContext) -> Response:
        """Create a draft without reserving a pet.

        :param context: Authenticated draft payload.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(
            public_order(self.data.create_draft(context.validated(OrderCreateRequest, V.order), actor)),
            status_code=201,
        )

    def updateOrderDraft(self, context: RequestContext) -> Response:
        """Replace editable fields of an owned draft.

        :param context: Authenticated draft UUID and payload.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(
            public_order(
                self.data.update_draft(
                    context.identifier("orderId"), context.validated(OrderCreateRequest, V.order), actor
                )
            )
        )

    def placeOrderDraft(self, context: RequestContext) -> Response:
        """Capture snapshots and reserve the draft's pet.

        :param context: Authenticated draft UUID.
        """
        return Responses(
            public_order(
                self.data.place_draft(context.identifier("orderId"), context.authorize("USER", "ADMIN"))
            )
        )

    def deleteOrder(self, context: RequestContext) -> Response:
        """Delete only a draft or an administrator-deletable terminal order.

        :param context: Authenticated order UUID.
        """
        self.data.delete_order(context.identifier("orderId"), context.authorize("USER", "ADMIN"))
        return Response(status_code=204)

    def transition(self, context: RequestContext, target: OrderStatus, admin_only: bool) -> Response:
        """Apply an authorized lifecycle action.

        :param context: Order UUID and Bearer token.
        :param target: Destination state.
        :param admin_only: Whether the action is restricted to ADMIN.
        """
        actor = context.authorize(*(("ADMIN",) if admin_only else ("USER", "ADMIN")))
        return Responses(public_order(self.data.transition(context.identifier("orderId"), target, actor)))

    def approveOrder(self, context: RequestContext) -> Response:
        """Approve a payable or preserved legacy order as ADMIN.

        :param context: Authenticated order UUID.
        """
        return self.transition(context, OrderStatus.APPROVED, True)

    def shipOrder(self, context: RequestContext) -> Response:
        """Ship an approved order as ADMIN.

        :param context: Authenticated order UUID.
        """
        return self.transition(context, OrderStatus.SHIPPED, True)

    def deliverOrder(self, context: RequestContext) -> Response:
        """Deliver a shipped order and mark its pet sold.

        :param context: Authenticated order UUID.
        """
        return self.transition(context, OrderStatus.DELIVERED, True)

    def cancelOrder(self, context: RequestContext) -> Response:
        """Cancel an owned eligible order and refund if paid.

        :param context: Authenticated order UUID.
        """
        return self.transition(context, OrderStatus.CANCELLED, False)
