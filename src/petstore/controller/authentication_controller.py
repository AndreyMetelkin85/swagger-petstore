"""Controllers preserve operation IDs, roles, response codes and service boundaries."""

from typing import cast

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.model.requests import (
    LoginRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses


class AuthenticationController:
    """Login and password-recovery operations."""

    def login(self, context: RequestContext) -> Response:
        """Authenticate an active account and issue a Bearer token.

        :param context: Login credentials.
        """
        request = context.validated(LoginRequest, V.login)
        return Responses(context.auth.login(cast(str, request.email), cast(str, request.password)))

    def forgotPassword(self, context: RequestContext) -> Response:
        """Generate a password-reset link with configured exposure.

        :param context: Recovery email.
        """
        request = context.validated(PasswordForgotRequest, V.forgot)
        return Responses(context.auth.forgot_password(cast(str, request.email)))

    def resetPassword(self, context: RequestContext) -> Response:
        """Consume the query code and set the JSON-body password.

        :param context: Parsed reset code and payload.
        """
        request = context.validated(PasswordResetRequest, V.reset)
        context.auth.reset_password(context.parameters["code"], cast(str, request.new_password))
        return Response(status_code=204)
