"""Типизированные модели и правила действующего контракта API."""

from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from petstore.model.enums import Role


class RequestModel(BaseModel):
    """Модель запроса, сохраняющая неизвестные поля для ошибок конкретной операции."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @classmethod
    def from_wire(cls, value: Any) -> Self:
        """Разбирает внешние JSON-имена, сохраняя snake_case конструкторов Python.

        :param value: JSON со внешними именами полей запроса.
        :return: Результат операции типа Self.
        """
        if isinstance(value, cls):
            return value
        return cls.model_validate(value, by_alias=True, by_name=False)


class Address(RequestModel):
    """Российский адрес доставки с действующими внешними именами полей."""

    city: str | None = None
    street: str | None = None
    house: str | None = None
    apartment: str | None = None
    postal_code: str | None = Field(None, alias="postalCode")


class RegisterRequest(RequestModel):
    """Регистрация; роль и состояние аккаунта назначает сервер."""

    username: str | None = None
    password: str | None = Field(None, repr=False)
    email: str | None = None
    first_name: str | None = Field(None, alias="firstName")
    last_name: str | None = Field(None, alias="lastName")
    phone: str | None = None
    address: Address | None = None


class LoginRequest(RequestModel):
    """Учётные данные входа и повторной отправки подтверждения."""

    email: str | None = None
    password: str | None = Field(None, repr=False)


class PasswordForgotRequest(RequestModel):
    """Email аккаунта для восстановления доступа."""

    email: str | None = None


class PasswordResetRequest(RequestModel):
    """Новый пароль; одноразовый код передаётся отдельно в query."""

    new_password: str | None = Field(None, alias="newPassword", repr=False)


class UserUpdateRequest(RequestModel):
    """Частичный профиль; явный null адреса удаляет сохранённый адрес."""

    first_name: str | None = Field(None, alias="firstName")
    last_name: str | None = Field(None, alias="lastName")
    phone: str | None = None
    address: Address | None = None


class AdminUserUpdateRequest(UserUpdateRequest):
    """Полное административное изменение аккаунта, включая имя, email и роль."""

    username: str | None = None
    email: str | None = None
    role: Role | None = None


class Category(RequestModel):
    """Вложенная категория питомца с идентификатором."""

    id: UUID | None = None
    name: str | None = None


class Tag(Category):
    """Поисковый тег питомца."""


class PetCreateRequest(RequestModel):
    """Данные создания питомца администратором."""

    name: str | None = None
    category: Category | None = None
    tags: list[Tag | None] | None = None
    photo_urls: list[str | None] | None = Field(None, alias="photoUrls")
    status: str | None = None
    price: Decimal | None = None


class PetUpdateRequest(PetCreateRequest):
    """Полное изменение питомца с защитой ожидаемой версией."""

    version: int | None = None


class OrderCreateRequest(RequestModel):
    """Редактируемый черновик; количество отдельного питомца равно единице."""

    pet_id: UUID | None = Field(None, alias="petId")
    quantity: int | None = None


class PaymentRequest(RequestModel):
    """Ввод тестовой карты; секретные реквизиты исключены из repr."""

    card_number: str | None = Field(None, alias="cardNumber", repr=False)
    expiry_month: int | None = Field(None, alias="expiryMonth")
    expiry_year: int | None = Field(None, alias="expiryYear")
    cvv: str | None = Field(None, repr=False)
    cardholder_name: str | None = Field(None, alias="cardholderName", repr=False)
