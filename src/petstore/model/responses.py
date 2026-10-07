"""Original named response DTOs with Python attributes and unchanged JSON aliases."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from petstore.model.commerce import Animal, Publication
from petstore.model.enums import (
    AccountStatus,
    OrderStatus,
    PaymentAttemptStatus,
    PaymentStatus,
    PetStatus,
    Role,
)
from petstore.utils.responses import json_default

WireTime = Annotated[datetime, PlainSerializer(json_default, return_type=str, when_used="json")]
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class ResponseModel(BaseModel):
    """Public DTOs reject extra fields, especially private database/security columns."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Address(ResponseModel):
    """Strict public address: private or unsupported nested fields cannot leak."""

    city: str
    street: str
    house: str
    apartment: str | None = None
    postal_code: str = Field(alias="postalCode")


class Category(ResponseModel):
    """Legacy pet category summary."""

    id: UUID | None = None
    name: str | None = None


class Tag(ResponseModel):
    """Legacy pet tag summary."""

    id: UUID | None = None
    name: str | None = None


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
    expires_at: WireTime = Field(alias="expiresAt")


class ConfirmationLinkResponse(ResponseModel):
    """Replacement confirmation URL and deadline."""

    confirmation_url: str = Field(alias="confirmationUrl")
    expires_at: WireTime = Field(alias="expiresAt")


class PasswordResetLinkResponse(ResponseModel):
    """Recovery deadline and optionally exposed test link."""

    reset_url: str | None = Field(alias="resetUrl")
    expires_at: WireTime = Field(alias="expiresAt")


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
    price: Money
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
    created_at: WireTime = Field(alias="createdAt")
    status: OrderStatus
    complete: bool
    unit_price: Money | None = Field(alias="unitPrice")
    total_amount: Money | None = Field(alias="totalAmount")
    currency: str
    delivery_details: DeliveryDetails | None = Field(alias="deliveryDetails")
    payment_status: PaymentStatus = Field(alias="paymentStatus")
    payment_expires_at: WireTime | None = Field(alias="paymentExpiresAt")
    ship_date: WireTime | None = Field(None, alias="shipDate")


class Payment(ResponseModel):
    """Safe payment summary without card number, CVV or request hash."""

    id: UUID
    order_id: UUID = Field(alias="orderId")
    amount: Money
    currency: str
    status: PaymentAttemptStatus
    card_brand: str = Field(alias="cardBrand")
    card_last4: str = Field(alias="cardLast4")
    failure_code: str | None = Field(None, alias="failureCode")
    created_at: WireTime = Field(alias="createdAt")
    updated_at: WireTime = Field(alias="updatedAt")


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
    timestamp: WireTime


class CatalogCategory(ResponseModel):
    """Versioned category; deactivation keeps its existing cards."""

    id: UUID
    name: str
    kind: Literal["product", "pet"]
    active: bool
    archived: bool
    version: int


class CatalogImage(ResponseModel):
    """Ordered image metadata, never a filesystem path."""

    media_id: UUID = Field(alias="mediaId")
    position: int
    alt: str
    is_cover: bool = Field(alias="isCover")
    image_url: str = Field(alias="imageUrl")
    thumb_url: str = Field(alias="thumbUrl")


class CatalogCard(ResponseModel):
    """Shared public card fields independent of the inventory type."""

    id: UUID
    name: str
    description: str
    category_id: UUID | None = Field(alias="categoryId")
    price: Money
    currency: Literal["RUB"]
    publication_status: Publication = Field(alias="publicationStatus")
    version: int
    images: list[CatalogImage]


class ProductCard(CatalogCard):
    """A product/feed card including current unreserved inventory."""

    kind: Literal["product"]
    sku: str
    brand: str
    product_type: Literal["FEED", "TREAT", "TOY", "ACCESSORY", "HYGIENE", "OTHER"] = Field(
        alias="productType"
    )
    animal_types: list[Animal] = Field(alias="animalTypes")
    feed_form: Literal["", "DRY", "WET"] = Field(alias="feedForm")
    life_stages: list[str] = Field(alias="lifeStages")
    net_weight_grams: int | None = Field(alias="netWeightGrams")
    ingredients: str
    stock: int
    reserved: int
    available_quantity: int = Field(alias="availableQuantity")


class PetCard(CatalogCard):
    """Extended pet card: availability remains separate from publication."""

    kind: Literal["pet"]
    animal_type: Animal = Field(alias="animalType")
    breed: str
    sex: Literal["MALE", "FEMALE", "UNKNOWN"]
    birth_date: date | None = Field(alias="birthDate")
    status: PetStatus
    photo_urls: list[str] = Field(alias="photoUrls")


class Page[Item: ResponseModel](ResponseModel):
    """Stable pagination envelope with typed card contents."""

    items: list[Item]
    page: int
    page_size: int = Field(alias="pageSize")
    total: int


ProductPage = Page[ProductCard]
PetPage = Page[PetCard]


class MediaMetadata(ResponseModel):
    """Sanitized image metadata without uploader identity or storage paths."""

    id: UUID
    name: str
    mime: str
    width: int
    height: int
    size: int
    source_type: Literal["OWN", "SUPPLIER", "DEMO"] = Field(alias="sourceType")
    source_note: str = Field(alias="sourceNote")
    created_at: WireTime = Field(alias="createdAt")
    image_url: str = Field(alias="imageUrl")
    thumb_url: str = Field(alias="thumbUrl")


class CartLine(ResponseModel):
    """Current availability and saved quote for one soft catalog reference."""

    id: UUID
    kind: Literal["product", "pet"]
    quantity: int
    name: str
    price: Money | None
    quoted_price: Money | None = Field(alias="quotedPrice")
    currency: Literal["RUB"]
    price_changed: bool = Field(alias="priceChanged")
    available: bool
    reason: str | None
    images: list[CatalogImage]


class Cart(ResponseModel):
    """Versioned mixed cart retaining unavailable positions."""

    lines: list[CartLine]
    version: int


class StoreOrderLine(ResponseModel):
    """Immutable checkout quote plus optional legacy-compatible allocation state."""

    kind: Literal["product", "pet"]
    item_id: UUID = Field(alias="itemId")
    name: str
    sku: str
    quantity: int
    price: Money | None
    images: list[CatalogImage]
    allocation: Literal["NONE", "RESERVED", "RELEASED", "CONSUMED"] | None = None


class StoreOrder(ResponseModel):
    """Mixed or adapted legacy order with typed immutable snapshots."""

    id: UUID
    user_id: UUID = Field(alias="userId")
    status: OrderStatus
    payment_status: PaymentStatus = Field(alias="paymentStatus")
    version: int
    cart_version: int | None = Field(alias="cartVersion")
    created_at: WireTime = Field(alias="createdAt")
    ship_date: WireTime | None = Field(alias="shipDate")
    payment_expires_at: WireTime | None = Field(alias="paymentExpiresAt")
    lines: list[StoreOrderLine]
    total: Money | None
    currency: Literal["RUB"]
    delivery: DeliveryDetails | None
    complete: bool
