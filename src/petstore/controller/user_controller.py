"""Controllers preserve operation IDs, roles, response codes and service boundaries."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.model.requests import (
    AdminUserUpdateRequest,
    UserUpdateRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses, public_user


class UserController:
    """Self-service profile and administrator account-management endpoints."""

    def get_current_user(self, context: RequestContext) -> Response:
        """Read the authenticated caller's public profile.

        :param context: Bearer-authenticated request.
        """
        return Responses(public_user(context.authorize("USER", "ADMIN")))

    def update_current_user(self, context: RequestContext) -> Response:
        """Apply a partial self-service profile update.

        :param context: Bearer-authenticated profile changes.
        """
        user = context.authorize("USER", "ADMIN")
        return Responses(
            public_user(
                context.auth.user_data.update_user(user, context.validated(UserUpdateRequest, V.user_update))
            )
        )

    def list_users(self, context: RequestContext) -> Response:
        """List public profiles only for an administrator.

        :param context: Administrator request.
        """
        context.authorize("ADMIN")
        return Responses([public_user(user) for user in context.auth.user_data.find_all()])

    def get_user_by_id(self, context: RequestContext) -> Response:
        """Read a target account as an administrator.

        :param context: Authorized target UUID.
        """
        context.authorize("ADMIN")
        return Responses(public_user(context.auth.required_user(context.identifier("userId"))))

    def update_user_by_id(self, context: RequestContext) -> Response:
        """Replace administrator-editable account data.

        :param context: Authorized target UUID and full profile.
        """
        context.authorize("ADMIN")
        request = context.validated(AdminUserUpdateRequest, V.admin_update)
        return Responses(
            public_user(context.auth.user_data.update_user_as_admin(context.identifier("userId"), request))
        )

    def delete_user_by_id(self, context: RequestContext) -> Response:
        """Delete an account without bypassing protected-account or order rules.

        :param context: Administrator and target UUID.
        """
        actor = context.authorize("ADMIN")
        context.auth.user_data.delete_user(actor, context.identifier("userId"))
        return Response(status_code=204)
