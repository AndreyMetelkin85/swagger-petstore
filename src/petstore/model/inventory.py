"""Типизированные модели и правила действующего контракта API."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from petstore.data.database import Row
from petstore.model.commerce import Publication
from petstore.model.enums import PetStatus
from petstore.service.exceptions import ApiException


class InventoryItem(BaseModel):
    """Проверенный неизменяемый снимок остатков под блокировкой строки."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: UUID
    kind: Literal["product", "pet"]
    name: str
    sku: str | None = ""
    price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    publication_status: Publication
    stock: int = Field(default=0, ge=0)
    reserved: int = Field(default=0, ge=0)
    status: PetStatus | None = None

    @classmethod
    def from_row(cls, kind: str, row: Row) -> "InventoryItem":
        """Проверяет данные драйвера до расчёта цены и доступности.

        :param kind: Тип позиции или категории: товар либо питомец.
        :param row: Строка базы данных для обработки или преобразования.
        :return: Результат операции типа 'InventoryItem'.
        """
        return cls.model_validate({**row, "kind": kind})

    def availability_reason(self, quantity: int) -> str | None:
        """Объясняет недоступность позиции, не удаляя ссылку покупателя из корзины.

        :param quantity: Количество единиц позиции; для питомца всегда одна.
        :return: Результат операции типа str | None.
        """
        if self.publication_status != Publication.PUBLISHED or self.price is None:
            return "PRODUCT_UNAVAILABLE" if self.kind == "product" else "PET_NOT_AVAILABLE"
        if self.kind == "product" and self.stock - self.reserved < quantity:
            return "INSUFFICIENT_STOCK"
        if self.kind == "pet" and self.status != PetStatus.AVAILABLE:
            return "PET_NOT_AVAILABLE"
        return None

    def checkout_amount(self, quoted_price: Decimal, quantity: int) -> Decimal:
        """Проверяет сохранённую цену и доступность заблокированной позиции перед записью резерва.

        :param quoted_price: Сохранённая цена для проверки изменения перед оформлением.
        :param quantity: Количество единиц позиции; для питомца всегда одна.
        :return: Результат операции типа Decimal.
        """
        if self.publication_status != Publication.PUBLISHED or self.price is None:
            raise ApiException(409, "PRODUCT_UNAVAILABLE", "A checkout item is unpublished")
        if self.price != quoted_price:
            raise ApiException(409, "PRICE_CHANGED", "A checkout price changed; refresh the cart")
        if self.kind == "product" and self.stock - self.reserved < quantity:
            raise ApiException(409, "INSUFFICIENT_STOCK", "Not enough unreserved stock")
        if self.kind == "pet" and self.status != PetStatus.AVAILABLE:
            raise ApiException(409, "PET_NOT_AVAILABLE", "Pet is already reserved or unavailable")
        return self.price * quantity
