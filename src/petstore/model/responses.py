"""Типизированные модели и правила действующего контракта API."""

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
    """Публичный DTO, запрещающий лишние поля и утечку приватных столбцов."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Address(ResponseModel):
    """Российский адрес доставки с действующими внешними именами полей."""

    city: str
    street: str
    house: str
    apartment: str | None = None
    postal_code: str = Field(alias="postalCode")


class Category(ResponseModel):
    """Вложенная категория питомца с идентификатором."""

    id: UUID | None = None
    name: str | None = None


class Tag(ResponseModel):
    """Поисковый тег питомца."""

    id: UUID | None = None
    name: str | None = None


class User(ResponseModel):
    """Публичный профиль без пароля, одноразовых кодов и версии токена."""

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
    """Неподтверждённый аккаунт, ссылка подтверждения и срок действия."""

    user: User
    confirmation_url: str = Field(alias="confirmationUrl")
    expires_at: WireTime = Field(alias="expiresAt")


class ConfirmationLinkResponse(ResponseModel):
    """Новая ссылка подтверждения и срок её действия."""

    confirmation_url: str = Field(alias="confirmationUrl")
    expires_at: WireTime = Field(alias="expiresAt")


class PasswordResetLinkResponse(ResponseModel):
    """Срок восстановления и необязательная видимая тестовая ссылка."""

    reset_url: str | None = Field(alias="resetUrl")
    expires_at: WireTime = Field(alias="expiresAt")


class LoginResponse(ResponseModel):
    """Bearer-токен и профиль авторизованного пользователя."""

    access_token: str = Field(repr=False)
    token_type: str
    expires_in: int
    user: User


class Pet(ResponseModel):
    """Публичный питомец с точной ценой и версией."""

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
    """Неизменяемый снимок контактов и адреса на момент оформления."""

    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    phone: str
    address: Address


class Order(ResponseModel):
    """Заказ с владельцем и сохранёнными снимками прежнего контракта."""

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
    """Безопасная сводка оплаты без номера карты, CVV и хеша запроса."""

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
    """Ошибка отдельного поля; бизнес-ошибки допускают пустой список деталей."""

    field: str
    message: str


class ErrorResponse(ResponseModel):
    """Общий ответ ошибки со статусом, кодом, сообщением и деталями."""

    status: int = Field(ge=400, le=599)
    error: str
    message: str
    details: list[ErrorDetail]


class HealthResponse(ResponseModel):
    """Готовность сервиса и PostgreSQL с временем проверки UTC."""

    status: str
    service: str
    database: str
    timestamp: WireTime


class CatalogCategory(ResponseModel):
    """Категория с версией; деактивация сохраняет связанные карточки."""

    id: UUID
    name: str
    kind: Literal["product", "pet"]
    active: bool
    archived: bool
    version: int


class CatalogImage(ResponseModel):
    """Метаданные изображения с порядком, без пути файловой системы."""

    media_id: UUID = Field(alias="mediaId")
    position: int
    alt: str
    is_cover: bool = Field(alias="isCover")
    image_url: str = Field(alias="imageUrl")
    thumb_url: str = Field(alias="thumbUrl")


class CatalogCard(ResponseModel):
    """Общие публичные поля карточек независимо от типа остатков."""

    id: UUID
    name: str
    description: str
    category_id: UUID | None = Field(alias="categoryId")
    price: Money | None
    currency: Literal["RUB"]
    publication_status: Publication = Field(alias="publicationStatus")
    version: int
    images: list[CatalogImage]


class ProductCard(CatalogCard):
    """Карточка товара или корма с текущим свободным остатком."""

    kind: Literal["product"]
    sku: str | None
    brand: str
    product_type: Literal["FEED", "TREAT", "TOY", "ACCESSORY", "HYGIENE", "OTHER"] | None = Field(
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
    """Расширенная карточка питомца с отдельной доступностью и публикацией."""

    kind: Literal["pet"]
    animal_type: Animal | None = Field(alias="animalType")
    breed: str
    sex: Literal["MALE", "FEMALE", "UNKNOWN"]
    birth_date: date | None = Field(alias="birthDate")
    status: PetStatus
    photo_urls: list[str] = Field(alias="photoUrls")


class Page[Item: ResponseModel](ResponseModel):
    """Пагинация с типизированными карточками."""

    items: list[Item]
    page: int
    page_size: int = Field(alias="pageSize")
    total: int


ProductPage = Page[ProductCard]
PetPage = Page[PetCard]


class MediaMetadata(ResponseModel):
    """Очищенные метаданные изображения без автора загрузки и путей хранения."""

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
    """Текущая доступность и сохранённая цена позиции корзины."""

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
    """Смешанная корзина с версией и сохранением недоступных позиций."""

    lines: list[CartLine]
    version: int


class StoreOrderLine(ResponseModel):
    """Неизменяемая позиция заказа с ценой и состоянием выделенного резерва."""

    kind: Literal["product", "pet"]
    item_id: UUID = Field(alias="itemId")
    name: str
    sku: str
    quantity: int
    price: Money | None
    images: list[CatalogImage]
    allocation: Literal["NONE", "RESERVED", "RELEASED", "CONSUMED"] | None = None


class StoreOrder(ResponseModel):
    """Смешанный либо адаптированный прежний заказ с типизированными снимками."""

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
