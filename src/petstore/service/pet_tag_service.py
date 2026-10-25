"""Фиксированный справочник тегов и совместимость ранее сохранённых меток питомцев."""

from types import MappingProxyType

from petstore.data.database import Row
from petstore.model.enums import PetTagName
from petstore.model.requests import PetUpdateRequest
from petstore.service.exceptions import PetException

PET_TAG_LABELS = MappingProxyType(
    {
        PetTagName.FRIENDLY: "Дружелюбный",
        PetTagName.VACCINATED: "Привит",
        PetTagName.STERILIZED: "Стерилизован",
        PetTagName.MICROCHIPPED: "Чипирован",
    }
)
UNKNOWN_TAG_MESSAGE = "Tag name must be selected from the pet tag catalog"


class PetTagService:
    """Публикует разрешённые теги без БД и защищает неизменённые исторические метки."""

    @staticmethod
    def list_tags() -> list[dict[str, str]]:
        """Возвращает фиксированный набор названий и подписей, не создавая клиентских UUID.

        :return: Список значений для выбора перед созданием или обновлением питомца.
        """
        return [{"name": name.value, "label": label} for name, label in PET_TAG_LABELS.items()]

    @staticmethod
    def is_known(name: str) -> bool:
        """Проверяет точное регистрозависимое совпадение с разрешённым названием.

        :param name: Название тега из команды клиента.
        :return: True, если название включено в фиксированный справочник.
        """
        return name in PET_TAG_LABELS

    @classmethod
    def validate_existing_tags(cls, request: PetUpdateRequest, current_tags: list[Row]) -> None:
        """Разрешает старые неизвестные метки только с неизменённой парой UUID и названия.

        Проверка вызывается после блокировки строки питомца. Новое произвольное имя нельзя
        добавить ни с клиентским UUID, ни путём переименования исторической метки.

        :param request: Проверенная команда полного обновления питомца.
        :param current_tags: Метки из заблокированной текущей строки БД.
        :return: Ничего не возвращает; при неизвестной новой метке формирует ошибку 422.
        """
        existing = {(str(tag["id"]), tag["name"]) for tag in current_tags}
        errors: list[Row] = []
        for index, tag in enumerate(request.tags or []):
            if tag is None or tag.name is None or cls.is_known(tag.name):
                continue
            if (str(tag.id), tag.name) not in existing:
                errors.append({"field": f"tags[{index}].name", "message": UNKNOWN_TAG_MESSAGE})
        if errors:
            raise PetException(422, "VALIDATION_ERROR", "Request validation failed", errors)
