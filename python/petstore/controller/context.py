"""Typed request context independent of FastAPI's automatic validation response."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar, cast
from uuid import UUID

from starlette.requests import Request

from petstore.data.database import Row
from petstore.model.requests import RequestModel
from petstore.service.auth_service import AuthService
from petstore.service.validation_service import Details, ValidationService

Model = TypeVar("Model", bound=RequestModel)


@dataclass
class RequestContext:
    """Parsed transport values passed to the unchanged controller responsibilities."""

    request: Request
    auth: AuthService
    parameters: Row
    body: RequestModel | None

    def authorize(self, *roles: str) -> Row:
        """Authorize the incoming Bearer token with operation-specific roles.

        :param roles: Allowed roles.
        """
        return self.auth.authorize(self.request.headers.get("Authorization"), *roles)

    def identifier(self, name: str) -> UUID:
        """Return a UUID already checked by the shared transport adapter.

        :param name: Public parameter name.
        """
        return cast(UUID, self.parameters[name])

    def validated(self, model: type[Model], validator: Callable[[Model], Details]) -> Model:
        """Apply the original business validator to a parsed request model.

        :param model: Expected request class.
        :param validator: Operation-specific validation function.
        """
        assert isinstance(self.body, model)
        ValidationService.ensure(validator(self.body))
        return self.body
