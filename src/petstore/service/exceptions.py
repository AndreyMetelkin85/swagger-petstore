"""Business exceptions translated to the unchanged public error envelope."""

from typing import Any


class ApiException(Exception):
    """A safe public error, independent of transport and database exceptions."""

    def __init__(
        self, status: int, code: str, message: str, details: list[dict[str, Any]] | None = None
    ) -> None:
        """Store the public status and error details without request values.

        :param status: HTTP response status.
        :param code: Stable machine-readable error code.
        :param message: Public error description.
        :param details: Field-level validation errors.
        """
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []


class AccountException(ApiException):
    """Account authentication, recovery or administration failure."""


class OrderException(ApiException):
    """Order access or lifecycle failure."""


class PaymentException(ApiException):
    """Payment access, idempotency or simulator failure."""


class PetException(ApiException):
    """Pet availability or optimistic version conflict."""
