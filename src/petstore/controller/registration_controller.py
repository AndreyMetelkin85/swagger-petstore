"""Controllers preserve operation IDs, roles, response codes and service boundaries."""

from typing import cast

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.model.requests import (
    LoginRequest,
    RegisterRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses, public_user


class RegistrationController:
    """Account registration and one-time confirmation operations."""

    def register(self, context: RequestContext) -> Response:
        """Register a pending account.

        :param context: Registration request context.
        """
        request = context.validated(RegisterRequest, V.registration)
        return Responses(context.auth.register(request), status_code=201)

    def confirm(self, context: RequestContext) -> Response:
        """Confirm an account using its path UUID and query code.

        :param context: Parsed confirmation parameters.
        """
        return Responses(
            public_user(context.auth.confirm(context.identifier("userId"), context.parameters["code"]))
        )

    def resendConfirmation(self, context: RequestContext) -> Response:
        """Replace an unconfirmed account's confirmation link.

        :param context: Account credentials.
        """
        request = context.validated(LoginRequest, V.login)
        return Responses(
            context.auth.resend_confirmation(cast(str, request.email), cast(str, request.password))
        )
