"""Values match existing PostgreSQL enums and the public OpenAPI contract."""

from enum import StrEnum


class Role(StrEnum):
    """Permissions assigned to a user account."""

    USER = "USER"
    ADMIN = "ADMIN"


class AccountStatus(StrEnum):
    """Account confirmation and blocking states."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class PetStatus(StrEnum):
    """Catalog availability independent of request validation."""

    AVAILABLE = "available"
    PENDING = "pending"
    RESERVED = "reserved"
    SOLD = "sold"


class OrderStatus(StrEnum):
    """Order states with the same explicit transition matrix as Java."""

    DRAFT = "draft"
    PLACED = "placed"
    APPROVED = "approved"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    def can_transition_to(self, target: "OrderStatus") -> bool:
        """Check a requested transition; expiration is handled separately.

        :param target: Requested destination state.
        """
        return target in {
            self.DRAFT: {self.PLACED},
            self.PLACED: {self.APPROVED, self.CANCELLED},
            self.APPROVED: {self.SHIPPED, self.CANCELLED},
            self.SHIPPED: {self.DELIVERED},
        }.get(self, set())

    @property
    def is_active(self) -> bool:
        """Whether an order prevents deletion and holds a pet reservation."""
        return self in {self.PLACED, self.APPROVED, self.SHIPPED}

    @property
    def is_complete(self) -> bool:
        """Whether the order is terminal."""
        return self in {self.DELIVERED, self.CANCELLED, self.EXPIRED}


class PaymentStatus(StrEnum):
    """Aggregate payment state stored on an order."""

    NOT_STARTED = "NOT_STARTED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNPAID = "UNPAID"
    PAID = "PAID"
    REFUNDED = "REFUNDED"
    EXPIRED = "EXPIRED"


class PaymentAttemptStatus(StrEnum):
    """Outcome of an individual simulated payment attempt."""

    SUCCEEDED = "SUCCEEDED"
    DECLINED = "DECLINED"
    REFUNDED = "REFUNDED"
