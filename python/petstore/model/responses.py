"""Original named response DTOs with Python attributes and unchanged JSON aliases."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from petstore.model.enums import (
    AccountStatus,
    OrderStatus,
    PaymentAttemptStatus,
    PaymentStatus,
    PetStatus,
    Role,
)
from petstore.model.requests import Address, Category, Tag


class ResponseModel(BaseModel):
    """Public DTOs reject extra fields, especially private database/security columns."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class User(ResponseModel):
    """Public account profile, without password, codes or token version."""

    id: UUID
    username: str
    first_name: str | None = Field(None, alias="firstName")
    last_name: str | None = Field(None, alias="lastName")
    email: str
    phone: str | None = None
    address: Address | None = None
    user_status: AccountStatus = Field(alias="userStatus")
    role: Role


class RegistrationResponse(ResponseModel):
    """Pending account, confirmation URL and deadline."""

    user: User
    confirmation_url: str = Field(alias="confirmationUrl")
    expires_at: datetime = Field(alias="expiresAt")


class ConfirmationLinkResponse(ResponseModel):
    """Replacement confirmation URL and deadline."""

    confirmation_url: str = Field(alias="confirmationUrl")
    expires_at: datetime = Field(alias="expiresAt")


class PasswordResetLinkResponse(ResponseModel):
    """Recovery deadline and optionally exposed test link."""

    reset_url: str | None = Field(alias="resetUrl")
    expires_at: datetime = Field(alias="expiresAt")


class LoginResponse(ResponseModel):
    """Bearer access token and authenticated user profile."""

    access_token: str = Field(repr=False)
    token_type: str
    expires_in: int
    user: User


class Pet(ResponseModel):
    """Public catalog data with exact price and optimistic version."""

    id: UUID
    name: str
    category: Category | None = None
    tags: list[Tag] | None = None
    photo_urls: list[str] | None = Field(None, alias="photoUrls")
    status: PetStatus
    version: int
    price: Decimal
    currency: str


class DeliveryDetails(ResponseModel):
    """Checkout-time contact/address snapshot, independent of later profile edits."""

    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    phone: str
    address: Address


class Order(ResponseModel):
    """Draft or placed order using the original owner and snapshot fields."""

    id: UUID
    pet_id: UUID = Field(alias="petId")
    user_id: UUID = Field(alias="userId")
    quantity: int
    created_at: datetime = Field(alias="createdAt")
    status: OrderStatus
    complete: bool
    unit_price: Decimal | None = Field(alias="unitPrice")
    total_amount: Decimal | None = Field(alias="totalAmount")
    currency: str
    delivery_details: DeliveryDetails | None = Field(alias="deliveryDetails")
    payment_status: PaymentStatus = Field(alias="paymentStatus")
    payment_expires_at: datetime | None = Field(alias="paymentExpiresAt")
    ship_date: datetime | None = Field(None, alias="shipDate")


class Payment(ResponseModel):
    """Safe payment summary without card number, CVV or request hash."""

    id: UUID
    order_id: UUID = Field(alias="orderId")
    amount: Decimal
    currency: str
    status: PaymentAttemptStatus
    card_brand: str = Field(alias="cardBrand")
    card_last4: str = Field(alias="cardLast4")
    failure_code: str | None = Field(None, alias="failureCode")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ErrorDetail(ResponseModel):
    """Field-specific error details, including empty-list-compatible business failures."""

    field: str
    message: str


class ErrorResponse(ResponseModel):
    """The four-field API error envelope retained by every controller."""

    status: int = Field(ge=400, le=599)
    error: str
    message: str
    details: list[ErrorDetail]


class HealthResponse(ResponseModel):
    """Service and PostgreSQL availability plus UTC probe time."""

    status: str
    service: str
    database: str
    timestamp: datetime
