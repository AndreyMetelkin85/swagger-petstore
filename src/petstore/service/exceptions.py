"""Бизнес-правила и согласование операций приложения."""

from typing import Any


class ApiException(Exception):
    """Публичная бизнес-ошибка, независимая от HTTP и исключений базы."""

    def __init__(
        self, status: int, code: str, message: str, details: list[dict[str, Any]] | None = None
    ) -> None:
        """Сохраняет публичный статус, код и детали ошибки без исходных значений запроса.

        :param status: Статус ресурса либо HTTP-ответа согласно операции.
        :param code: Стабильный машинный код публичной ошибки.
        :param message: Публичное описание ошибки без исходных значений запроса.
        :param details: Безопасные детали ошибок отдельных полей.
        :return: Ничего не возвращает.
        """
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []


class AccountException(ApiException):
    """Ошибка входа, восстановления или управления аккаунтом."""


class OrderException(ApiException):
    """Ошибка доступа либо жизненного цикла заказа."""


class PaymentException(ApiException):
    """Ошибка доступа, идемпотентности либо симуляции оплаты."""


class PetException(ApiException):
    """Ошибка доступности питомца или конфликта версии."""
