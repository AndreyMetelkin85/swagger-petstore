"""Transport types; business validation deliberately preserves original errors."""

from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from petstore.model.enums import Role


class RequestModel(BaseModel):
    """Retain unknown fields so each operation can report its own validation errors."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @classmethod
    def from_wire(cls, value: Any) -> Self:
        """Validate HTTP aliases without changing Python-side constructor ergonomics.

        :param value: JSON object supplied to the native FastAPI body field.
        :raises ValidationError: A field has an incompatible type or value.
        """
        if isinstance(value, cls):
            return value
        return cls.model_validate(value, by_alias=True, by_name=False)


class Address(RequestModel):
    """Russian delivery address, with original external field names."""

    city: str | None = None
    street: str | None = None
    house: str | None = None
    apartment: str | None = None
    postal_code: str | None = Field(None, alias="postalCode")


class RegisterRequest(RequestModel):
    """New account data; role and account status are assigned by the server."""

    username: str | None = None
    password: str | None = Field(None, repr=False)
    email: str | None = None
    first_name: str | None = Field(None, alias="firstName")
    last_name: str | None = Field(None, alias="lastName")
    phone: str | None = None
    address: Address | None = None


class LoginRequest(RequestModel):
    """Credentials used for login and resending confirmation links."""

    email: str | None = None
    password: str | None = Field(None, repr=False)


class PasswordForgotRequest(RequestModel):
    """Email identifying the account to recover."""

    email: str | None = None


class PasswordResetRequest(RequestModel):
    """New password; the one-time code remains a query parameter."""

    new_password: str | None = Field(None, alias="newPassword", repr=False)


class UserUpdateRequest(RequestModel):
    """Partial profile update; explicit null address clears the saved address."""

    first_name: str | None = Field(None, alias="firstName")
    last_name: str | None = Field(None, alias="lastName")
    phone: str | None = None
    address: Address | None = None


class AdminUserUpdateRequest(UserUpdateRequest):
    """Full administrator update, including username, email and role."""

    username: str | None = None
    email: str | None = None
    role: Role | None = None


class Category(RequestModel):
    """Nested pet category with a server-generated identifier when omitted."""

    id: UUID | None = None
    name: str | None = None


class Tag(Category):
    """Nested searchable pet tag."""


class PetCreateRequest(RequestModel):
    """Administrator-managed pet creation data."""

    name: str | None = None
    category: Category | None = None
    tags: list[Tag | None] | None = None
    photo_urls: list[str | None] | None = Field(None, alias="photoUrls")
    status: str | None = None
    price: Decimal | None = None


class PetUpdateRequest(PetCreateRequest):
    """Full pet update protected by an optimistic version check."""

    version: int | None = None


class OrderCreateRequest(RequestModel):
    """Editable draft fields; quantity is one for an individual pet."""

    pet_id: UUID | None = Field(None, alias="petId")
    quantity: int | None = None


class PaymentRequest(RequestModel):
    """Test-card payment input; sensitive values are never included in repr."""

    card_number: str | None = Field(None, alias="cardNumber", repr=False)
    expiry_month: int | None = Field(None, alias="expiryMonth")
    expiry_year: int | None = Field(None, alias="expiryYear")
    cvv: str | None = Field(None, repr=False)
    cardholder_name: str | None = Field(None, alias="cardholderName", repr=False)
