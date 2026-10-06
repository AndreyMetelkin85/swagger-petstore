"""Controllers preserve operation IDs, roles, response codes and service boundaries."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.utils.responses import Responses, public_user


class AdminUserController:
    """Administrator block/unblock actions separate from profile editing."""

    def blockUser(self, context: RequestContext) -> Response:
        """Block a user and invalidate existing access tokens.

        :param context: Administrator and target account.
        """
        actor = context.authorize("ADMIN")
        return Responses(public_user(context.auth.set_blocked(actor, context.identifier("userId"), True)))

    def unblockUser(self, context: RequestContext) -> Response:
        """Restore a blocked account's confirmed or pending state.

        :param context: Administrator and target account.
        """
        actor = context.authorize("ADMIN")
        return Responses(public_user(context.auth.set_blocked(actor, context.identifier("userId"), False)))
