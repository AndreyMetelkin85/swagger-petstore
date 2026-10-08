"""Бизнес-правила и согласование операций приложения."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from petstore.model.requests import (
    Address,
    AdminUserUpdateRequest,
    LoginRequest,
    OrderCreateRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    PaymentRequest,
    PetCreateRequest,
    PetUpdateRequest,
    RegisterRequest,
    RequestModel,
    UserUpdateRequest,
)
from petstore.service.exceptions import ApiException

Details = list[dict[str, Any]]


class ValidationService:
    """Бизнес-валидация для HTTP-адаптеров и unit-тестов."""

    USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
    EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    PHONE = re.compile(r"^\+?[0-9 ()-]+$")
    TEST_CARDS = {"4242424242424242", "4000000000000002", "4000000000009995"}

    @staticmethod
    def add(errors: Details, field: str, message: str) -> None:
        """Добавляет ошибку в действующем формате ErrorDetail.

        :param errors: Список ошибок, который дополняется в порядке проверок.
        :param field: Публичное имя проверяемого поля.
        :param message: Публичное описание ошибки без исходных значений запроса.
        :return: Ничего не возвращает.
        """
        errors.append({"field": field, "message": message})

    @staticmethod
    def ensure(errors: Details) -> None:
        """Формирует общую ошибку 422 при наличии ошибок валидации.

        :param errors: Список ошибок, который дополняется в порядке проверок.
        :return: Ничего не возвращает.
        """
        if errors:
            raise ApiException(422, "VALIDATION_ERROR", "Request validation failed", errors)

    @classmethod
    def text(cls, field: str, value: str | None, limit: int, errors: Details, required: bool = False) -> None:
        """Проверяет обязательный или необязательный текст без изменения значения.

        :param field: Публичное имя проверяемого поля.
        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :param limit: Серверное ограничение длины или размера обрабатываемой пачки.
        :param errors: Список ошибок, который дополняется в порядке проверок.
        :param required: Считать ли отсутствие значения ошибкой.
        :return: Ничего не возвращает.
        """
        if value is None:
            if required:
                cls.add(errors, field, "Field is required")
        elif not value.strip():
            cls.add(errors, field, "Field is required" if required else f"{field} must not be blank")
        elif len(value) > limit:
            cls.add(errors, field, f"{field} must not exceed {limit} characters")

    @classmethod
    def email(cls, value: str | None, errors: Details) -> None:
        """Проверяет email по действующему серверному шаблону.

        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :param errors: Список ошибок, который дополняется в порядке проверок.
        :return: Ничего не возвращает.
        """
        if value is None or not value.strip():
            cls.add(errors, "email", "Email is required")
        elif len(value) > 254 or not cls.EMAIL.fullmatch(value):
            cls.add(errors, "email", "Email must be a valid email address")

    @classmethod
    def password(cls, value: str | None, errors: Details, field: str = "password") -> None:
        """Проверяет ограничения длины пароля в символах и UTF-8-байтах для bcrypt.

        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :param errors: Список ошибок, который дополняется в порядке проверок.
        :param field: Публичное имя проверяемого поля.
        :return: Ничего не возвращает.
        """
        if not value:
            cls.add(errors, field, "Password is required")
        elif not 6 <= len(value) <= 100:
            cls.add(errors, field, "Password must be between 6 and 100 characters")
        elif len(value.encode("utf-8")) > 72:
            cls.add(errors, field, "Password must not exceed 72 UTF-8 bytes")

    @classmethod
    def phone(cls, value: str | None, errors: Details) -> None:
        """Проверяет необязательный номер телефона.

        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :param errors: Список ошибок, который дополняется в порядке проверок.
        :return: Ничего не возвращает.
        """
        if value is not None and (not 7 <= len(value) <= 30 or not cls.PHONE.fullmatch(value)):
            cls.add(errors, "phone", "Phone must contain 7-30 digits and phone punctuation")

    @classmethod
    def address(cls, value: Address | None, errors: Details) -> None:
        """Проверяет непустой российский адрес доставки.

        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :param errors: Список ошибок, который дополняется в порядке проверок.
        :return: Ничего не возвращает.
        """
        if value is None:
            return
        for name, limit in (("city", 100), ("street", 150), ("house", 30)):
            cls.text(f"address.{name}", getattr(value, name), limit, errors, True)
        cls.text("address.apartment", value.apartment, 30, errors)
        if value.postal_code is None or not re.fullmatch(r"[0-9]{6}", value.postal_code):
            cls.add(errors, "address.postalCode", "Postal code must contain exactly six digits")
        cls.extras(value, "Field is not allowed in a Russian delivery address", errors, "address.")

    @classmethod
    def extras(cls, model: RequestModel, message: str, errors: Details, prefix: str = "") -> None:
        """Сообщает о неподдерживаемых полях в порядке их передачи.

        :param model: Ожидаемая модель разобранного запроса.
        :param message: Публичное описание ошибки без исходных значений запроса.
        :param errors: Список ошибок, который дополняется в порядке проверок.
        :param prefix: Префикс составного имени вложенного поля.
        :return: Ничего не возвращает.
        """
        for field in model.model_extra or {}:
            cls.add(errors, prefix + field, message)

    @classmethod
    def username(cls, value: str | None, errors: Details) -> None:
        """Проверяет имя пользователя по действующему набору разрешённых символов.

        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :param errors: Список ошибок, который дополняется в порядке проверок.
        :return: Ничего не возвращает.
        """
        if value is None or not value.strip():
            cls.add(errors, "username", "Username is required")
        elif not cls.USERNAME.fullmatch(value):
            cls.add(
                errors,
                "username",
                "Username must be 3-30 characters and contain only letters, digits, dot, underscore or hyphen",
            )

    @classmethod
    def registration(cls, request: RegisterRequest) -> Details:
        """Проверяет регистрацию в порядке, совместимом с прежней реализацией.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        cls.username(request.username, errors)
        cls.password(request.password, errors)
        cls.email(request.email, errors)
        cls.text("firstName", request.first_name, 50, errors)
        cls.text("lastName", request.last_name, 50, errors)
        cls.phone(request.phone, errors)
        cls.address(request.address, errors)
        return errors

    @classmethod
    def login(cls, request: LoginRequest) -> Details:
        """Проверяет вход и повторную отправку ссылки без ограничений регистрации для пароля.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        cls.email(request.email, errors)
        if not request.password:
            cls.add(errors, "password", "Password is required")
        return errors

    @classmethod
    def forgot(cls, request: PasswordForgotRequest) -> Details:
        """Проверяет email запроса восстановления пароля.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        cls.email(request.email, errors)
        return errors

    @classmethod
    def reset(cls, request: PasswordResetRequest) -> Details:
        """Проверяет новый пароль для восстановления аккаунта.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        cls.password(request.new_password, errors, "newPassword")
        return errors

    @classmethod
    def user_update(cls, request: UserUpdateRequest) -> Details:
        """Проверяет частичное изменение профиля, включая явное удаление адреса.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        cls.extras(request, "Field is not allowed for profile update", errors)
        cls.text("firstName", request.first_name, 50, errors)
        cls.text("lastName", request.last_name, 50, errors)
        cls.phone(request.phone, errors)
        cls.address(request.address, errors)
        if (
            all(value is None for value in (request.first_name, request.last_name, request.phone))
            and "address" not in request.model_fields_set
        ):
            cls.add(errors, "body", "At least one profile field is required")
        return errors

    @classmethod
    def admin_update(cls, request: AdminUserUpdateRequest) -> Details:
        """Проверяет полный профиль, редактируемый администратором.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        cls.extras(request, "Field is not allowed for administrator profile update", errors)
        cls.username(request.username, errors)
        cls.email(request.email, errors)
        cls.text("firstName", request.first_name, 50, errors)
        cls.text("lastName", request.last_name, 50, errors)
        cls.phone(request.phone, errors)
        cls.address(request.address, errors)
        if "address" not in request.model_fields_set:
            cls.add(errors, "address", "Address field is required and may be null")
        if request.role is None:
            cls.add(errors, "role", "Role is required")
        return errors

    @classmethod
    def pet(cls, request: PetCreateRequest) -> Details:
        """Проверяет поля питомца и запрещает изменение серверных полей.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        if request.name is None or not request.name.strip():
            cls.add(errors, "name", "Pet name is required")
        elif len(request.name) > 100:
            cls.add(errors, "name", "Pet name must not exceed 100 characters")
        price = request.price
        if price is None:
            cls.add(errors, "price", "Pet price is required")
        elif price < Decimal("0.01"):
            cls.add(errors, "price", "Pet price must be at least 0.01")
        elif isinstance(price.as_tuple().exponent, int) and int(price.as_tuple().exponent) < -2:
            cls.add(errors, "price", "Pet price must have no more than two decimal places")
        elif price > Decimal("9999999999.99"):
            cls.add(errors, "price", "Pet price is too large")
        if request.status == "reserved":
            cls.add(errors, "status", "Reserved status is managed by the order lifecycle")
        elif request.status is not None and request.status not in {"available", "pending", "sold"}:
            cls.add(errors, "status", "Pet status must be available, pending or sold")
        if request.category is not None:
            value = request.category.name
            if value is None or not value.strip():
                cls.add(errors, "category.name", "Category name is required")
            elif len(value) > 50:
                cls.add(errors, "category.name", "Category name must not exceed 50 characters")
        if request.tags is not None:
            if len(request.tags) > 20:
                cls.add(errors, "tags", "No more than 20 tags are allowed")
            for index, tag in enumerate(request.tags):
                field = f"tags[{index}].name"
                if tag is None or tag.name is None or not tag.name.strip():
                    cls.add(errors, field, "Tag name is required")
                elif len(tag.name) > 30:
                    cls.add(errors, field, "Tag name must not exceed 30 characters")
                elif not re.fullmatch(r"[A-Za-z0-9_.-]+", tag.name):
                    cls.add(
                        errors, field, "Tag name may contain only letters, digits, dot, underscore or hyphen"
                    )
        if request.photo_urls is not None:
            if len(request.photo_urls) > 20:
                cls.add(errors, "photoUrls", "No more than 20 photo URLs are allowed")
            for index, url in enumerate(request.photo_urls):
                field = f"photoUrls[{index}]"
                if url is None or not url.strip():
                    cls.add(errors, field, "Photo URL is required")
                elif len(url) > 2048:
                    cls.add(errors, field, "Photo URL must not exceed 2048 characters")
                else:
                    try:
                        if any(char.isspace() for char in url):
                            raise ValueError("Whitespace is not valid in a URI")
                        if not urlsplit(url).scheme:
                            cls.add(errors, field, "Photo URL must be an absolute URI")
                    except ValueError:
                        cls.add(errors, field, "Photo URL must be a valid URI")
        cls.extras(request, "Field is not allowed for this operation", errors)
        if isinstance(request, PetUpdateRequest):
            if request.version is None:
                cls.add(errors, "version", "Pet version is required")
            elif request.version < 0:
                cls.add(errors, "version", "Pet version must not be negative")
        return errors

    @classmethod
    def order(cls, request: OrderCreateRequest) -> Details:
        """Проверяет два редактируемых поля черновика заказа.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        if request.pet_id is None:
            cls.add(errors, "petId", "Pet id is required and must be a valid UUID")
        if request.quantity != 1:
            cls.add(errors, "quantity", "Quantity must be 1 for an individual pet")
        cls.extras(request, "Field is managed by the server", errors)
        return errors

    @classmethod
    def missing_order_profile_fields(cls, user: dict[str, Any] | None) -> Details:
        """Возвращает отсутствующие данные оформления с публичными составными именами полей.

        :param user: Строка пользователя, полученная из базы данных.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        if user is None:
            return [{"field": "user", "message": "User profile is required"}]
        fields = {
            "firstName": "first_name",
            "lastName": "last_name",
            "phone": "phone",
            "address.city": "address_city",
            "address.street": "address_street",
            "address.house": "address_house",
            "address.postalCode": "address_postal_code",
        }
        for public, column in fields.items():
            if not user.get(column) or not str(user[column]).strip():
                cls.add(errors, public, "Field is required to place an order")
        return errors

    @staticmethod
    def passes_luhn(value: str) -> bool:
        """Проверяет контрольную сумму карты без обращения к платёжному провайдеру.

        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :return: True при выполнении проверяемого условия, иначе False.
        """
        if not re.fullmatch(r"[0-9]{13,19}", value):
            return False
        digits = [int(char) for char in reversed(value)]
        return (
            sum(
                digit if index % 2 == 0 else (digit * 2 - 9 if digit > 4 else digit * 2)
                for index, digit in enumerate(digits)
            )
            % 10
            == 0
        )

    @classmethod
    def payment(cls, request: PaymentRequest) -> Details:
        """Проверяет поддерживаемые тестовые карты, срок действия и данные владельца.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Details.
        """
        errors: Details = []
        if request.card_number is None or not cls.passes_luhn(request.card_number):
            cls.add(errors, "cardNumber", "Card number must be valid and pass the Luhn check")
        elif request.card_number not in cls.TEST_CARDS:
            cls.add(errors, "cardNumber", "Use one of the documented test card numbers")
        month, year = request.expiry_month, request.expiry_year
        if month is None or not 1 <= month <= 12:
            cls.add(errors, "expiryMonth", "Expiry month must be between 1 and 12")
        now = datetime.now(UTC)
        if year is None:
            cls.add(errors, "expiryYear", "Expiry year is required")
        elif month is not None and 1 <= month <= 12 and (year, month) < (now.year, now.month):
            cls.add(errors, "expiryYear", "Card expiry date must not be in the past")
        if request.cvv is None or not re.fullmatch(r"[0-9]{3,4}", request.cvv):
            cls.add(errors, "cvv", "CVV must contain three or four digits")
        if request.cardholder_name is None or not request.cardholder_name.strip():
            cls.add(errors, "cardholderName", "Cardholder name is required")
        elif len(request.cardholder_name) > 100:
            cls.add(errors, "cardholderName", "Cardholder name must not exceed 100 characters")
        cls.extras(request, "Field is not allowed for payment", errors)
        return errors
