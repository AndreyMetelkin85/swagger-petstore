"""Типизированные модели и правила действующего контракта API."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self, cast
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from petstore.model.requests import RequestModel


class CommerceRequest(RequestModel):
    """Команда магазина, запрещающая неподдерживаемые и управляемые сервером поля."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class Publication(StrEnum):
    """Публикация карточки независимо от доступного остатка."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class Animal(StrEnum):
    """Поддерживаемые виды животных и фильтры аудитории."""

    DOG = "dog"
    CAT = "cat"
    BIRD = "bird"
    RODENT = "rodent"
    FISH = "fish"
    REPTILE = "reptile"
    OTHER = "other"


class LifeStage(StrEnum):
    """Возрастные группы корма; ALL не совмещается с отдельными группами."""

    YOUNG = "YOUNG"
    ADULT = "ADULT"
    SENIOR = "SENIOR"
    ALL = "ALL"


class ImageReference(CommerceRequest):
    """Изображение галереи с порядком и признаком единственной обложки."""

    media_id: UUID = Field(alias="mediaId")
    alt: str = Field(default="", max_length=300)
    is_cover: bool = Field(default=False, alias="isCover")


class CategoryCommand(CommerceRequest):
    """Создание или обновление категории по версии; деактивация сохраняет карточки."""

    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern="^(product|pet)$")
    active: bool = True
    version: int | None = Field(default=None, ge=0)


class ProductCommand(CommerceRequest):
    """Полная карточка товара; остаток меняется отдельной командой."""

    sku: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=5000)
    category_id: UUID | None = Field(default=None, alias="categoryId")
    brand: str = Field(default="", max_length=100)
    product_type: str | None = Field(
        default=None, alias="productType", pattern="^(FEED|TREAT|TOY|ACCESSORY|HYGIENE|OTHER)$"
    )
    animal_types: list[Animal] = Field(default_factory=list[Animal], alias="animalTypes", max_length=7)
    price: Decimal | None = Field(default=None, ge=0, le=Decimal("9999999999.99"), multiple_of=0.01)
    feed_form: str = Field(default="", alias="feedForm", pattern="^(|DRY|WET)$")
    life_stages: list[LifeStage] = Field(
        default_factory=list[LifeStage],
        alias="lifeStages",
        max_length=20,
        description="Unique age groups; ALL cannot be combined with specific stages.",
        json_schema_extra={"uniqueItems": True},
    )
    net_weight_grams: int | None = Field(default=None, alias="netWeightGrams", ge=1, le=1000000)
    ingredients: str = Field(default="", max_length=5000)
    images: list[ImageReference] = Field(default_factory=list[ImageReference], max_length=20)
    version: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0, le=1000000)

    @field_validator("life_stages", mode="before")
    @classmethod
    def validate_life_stages(cls, value: object) -> object:
        """Отклоняет недопустимые возрастные группы корма, включая неполные черновики.

        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :return: Результат операции типа object.
        """
        if not isinstance(value, list):
            return value
        stages = cast(list[object], value)
        allowed = {stage.value for stage in LifeStage}
        if any(not isinstance(stage, str) or stage not in allowed for stage in stages):
            raise ValueError("Unsupported life stage")
        if len(set(stages)) != len(stages) or (LifeStage.ALL in stages and len(stages) != 1):
            raise ValueError("Life stages must be unique; ALL cannot be combined with other stages")
        return stages

    @model_validator(mode="after")
    def validate_product_gallery(self) -> Self:
        """Отклоняет дубликаты изображений и обложек без требования заполнить весь черновик.

        :return: Результат операции типа Self.
        """
        validate_gallery(self.images)
        return self


class PetCardCommand(CommerceRequest):
    """Расширенная карточка питомца без клиентского управления резервом и публикацией."""

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    animal_type: Animal | None = Field(default=None, alias="animalType")
    category_id: UUID | None = Field(default=None, alias="categoryId")
    breed: str = Field(default="", max_length=100)
    sex: str = Field(default="UNKNOWN", pattern="^(MALE|FEMALE|UNKNOWN)$")
    birth_date: date | None = Field(default=None, alias="birthDate")
    price: Decimal | None = Field(default=None, ge=0, le=Decimal("9999999999.99"), multiple_of=0.01)
    images: list[ImageReference] = Field(default_factory=list[ImageReference], max_length=20)
    version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_pet(self) -> Self:
        """Отклоняет будущую дату рождения и неоднозначный выбор обложки питомца.

        :return: Результат операции типа Self.
        """
        validate_gallery(self.images)
        if self.birth_date is not None and self.birth_date > date.today():
            raise ValueError("Birth date cannot be in the future")
        return self


def validate_gallery(images: list[ImageReference]) -> None:
    """Проверяет уникальность изображений и единственную обложку до получения блокировок базы.

    :param images: Проверенные элементы галереи в порядке отображения.
    :return: Ничего не возвращает.
    """
    if (
        len({image.media_id for image in images}) != len(images)
        or sum(image.is_cover for image in images) > 1
    ):
        raise ValueError("Gallery must contain unique media IDs and at most one cover")


class VersionCommand(CommerceRequest):
    """Ожидаемая версия для публикации и действий жизненного цикла."""

    version: int = Field(ge=0)


class StockCommand(VersionCommand):
    """Корректировка остатка с причиной; зарезервированные единицы нельзя убрать."""

    delta: int = Field(ge=-1000000, le=1000000)
    reason: str = Field(min_length=1, max_length=300)


class CartLineCommand(CommerceRequest):
    """Ссылка на позицию, сохраняемая в корзине даже при недоступности."""

    kind: str = Field(pattern="^(product|pet)$")
    id: UUID
    quantity: int = Field(ge=1, le=1000000)

    @model_validator(mode="after")
    def validate_quantity(self) -> Self:
        """Проверяет, что количество отдельного питомца равно единице.

        :return: Результат операции типа Self.
        """
        if self.kind == "pet" and self.quantity != 1:
            raise ValueError("Quantity must be 1 for an individual pet")
        return self


class CartCommand(VersionCommand):
    """Полная замена корзины по версии с защитой повторного объединения."""

    lines: list[CartLineCommand] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_lines(self) -> Self:
        """Отклоняет повторяющиеся позиции вместо суммирования дубликатов при объединении корзины.

        :return: Результат операции типа Self.
        """
        if len({(line.kind, line.id) for line in self.lines}) != len(self.lines):
            raise ValueError("Cart must contain unique items")
        return self


class CheckoutCommand(CommerceRequest):
    """Создание снимка известной версии серверной корзины."""

    cart_version: int = Field(alias="cartVersion", ge=1)


class TelemetryEvent(CommerceRequest):
    """Разрешённая телеметрия без произвольных строк и личных данных."""

    event: str = Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")
    method: str | None = Field(default=None, pattern="^(GET|POST|PUT|DELETE|PATCH)$")
    http_status: int | None = Field(default=None, alias="httpStatus", ge=100, le=599)
    duration_ms: int | None = Field(default=None, alias="durationMs", ge=0, le=3600000)
    request_id: UUID | None = Field(default=None, alias="requestId")
    error_code: str | None = Field(default=None, alias="errorCode", pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    resource_id: UUID | None = Field(default=None, alias="resourceId")
    route_id: str | None = Field(default=None, alias="routeId", max_length=160)
    endpoint_template: str | None = Field(default=None, alias="endpointTemplate", max_length=160)
    timestamp: datetime | None = None

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        """Проверяет часовой пояс времени события; произвольные строки не попадают в логи.

        :return: Результат операции типа Self.
        """
        if self.timestamp is not None and self.timestamp.tzinfo is None:
            raise ValueError("Event timestamp must contain a timezone")
        return self


class TelemetryCommand(CommerceRequest):
    """Ограниченная пачка событий с отклонением неизвестных метаданных."""

    events: list[TelemetryEvent] = Field(min_length=1, max_length=100)
