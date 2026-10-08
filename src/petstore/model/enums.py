"""Типизированные модели и правила действующего контракта API."""

from enum import StrEnum


class Role(StrEnum):
    """Роль аккаунта и его права."""

    USER = "USER"
    ADMIN = "ADMIN"


class AccountStatus(StrEnum):
    """Состояние подтверждения и блокировки аккаунта."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class PetStatus(StrEnum):
    """Доступность питомца, независимая от публикации карточки."""

    AVAILABLE = "available"
    PENDING = "pending"
    RESERVED = "reserved"
    SOLD = "sold"


class OrderStatus(StrEnum):
    """Состояния заказа и явная матрица разрешённых переходов."""

    DRAFT = "draft"
    PLACED = "placed"
    APPROVED = "approved"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    def can_transition_to(self, target: "OrderStatus") -> bool:
        """Проверяет разрешённый переход; истечение резерва обрабатывается отдельно.

        :param target: Целевое состояние жизненного цикла.
        :return: True при выполнении проверяемого условия, иначе False.
        """
        return target in {
            self.DRAFT: {self.PLACED},
            self.PLACED: {self.APPROVED, self.CANCELLED},
            self.APPROVED: {self.SHIPPED, self.CANCELLED},
            self.SHIPPED: {self.DELIVERED},
        }.get(self, set())

    @property
    def is_active(self) -> bool:
        """Определяет, удерживает ли заказ резерв и запрещает ли удаление.

        :return: True при выполнении проверяемого условия, иначе False.
        """
        return self in {self.PLACED, self.APPROVED, self.SHIPPED}

    @property
    def is_complete(self) -> bool:
        """Определяет, завершён ли жизненный цикл заказа.

        :return: True при выполнении проверяемого условия, иначе False.
        """
        return self in {self.DELIVERED, self.CANCELLED, self.EXPIRED}


class PaymentStatus(StrEnum):
    """Общее состояние оплаты заказа."""

    NOT_STARTED = "NOT_STARTED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNPAID = "UNPAID"
    PAID = "PAID"
    REFUNDED = "REFUNDED"
    EXPIRED = "EXPIRED"


class PaymentAttemptStatus(StrEnum):
    """Результат отдельной попытки тестовой оплаты."""

    SUCCEEDED = "SUCCEEDED"
    DECLINED = "DECLINED"
    REFUNDED = "REFUNDED"
