"""Serialize exact Decimal numbers and prevent security fields from leaking."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import simplejson
from starlette.responses import Response

from petstore.data.database import Row


def json_default(value: Any) -> str:
    """Serialize identifiers and UTC timestamps without changing monetary precision.

    :param value: A UUID or timezone-aware timestamp.
    """
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    raise TypeError(f"Unsupported response type: {type(value).__name__}")


class Responses(Response):
    """Original JSON wire format, including numeric Decimal values and UTF-8 text."""

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        """Render safe response data without floating-point money conversion.

        :param content: Public response payload.
        """
        return simplejson.dumps(
            content,
            ensure_ascii=False,
            use_decimal=True,
            allow_nan=False,
            default=json_default,
            separators=(",", ":"),
        ).encode("utf-8")


def public_user(row: Row) -> Row:
    """Expose only the original User fields, never passwords or link hashes.

    :param row: Private persisted user row.
    """
    address = None
    if row.get("address_city") is not None:
        address = {
            "city": row["address_city"],
            "street": row["address_street"],
            "house": row["address_house"],
            "apartment": row["address_apartment"],
            "postalCode": row["address_postal_code"],
        }
    return {
        "id": row["id"],
        "username": row["username"],
        "firstName": row["first_name"],
        "lastName": row["last_name"],
        "email": row["email"],
        "phone": row["phone"],
        "address": address,
        "userStatus": row["user_status"],
        "role": row["role"],
    }


def public_order(row: Row) -> Row:
    """Map SQL snapshot columns to the existing order contract.

    :param row: Persisted order row.
    """
    mapping = {
        "id": "id",
        "petId": "pet_id",
        "userId": "owner_user_id",
        "createdAt": "created_at",
        "quantity": "quantity",
        "status": "status",
        "unitPrice": "unit_price",
        "totalAmount": "total_amount",
        "currency": "currency",
        "deliveryDetails": "delivery_details",
        "paymentStatus": "payment_status",
        "paymentExpiresAt": "payment_expires_at",
        "shipDate": "ship_date",
        "complete": "complete",
    }
    return {public: row[column] for public, column in mapping.items()}


def public_payment(row: Row) -> Row:
    """Expose only payment summary fields; hide request hashes and idempotency keys.

    :param row: Persisted payment attempt.
    """
    mapping = {
        "id": "id",
        "orderId": "order_id",
        "amount": "amount",
        "currency": "currency",
        "status": "status",
        "cardBrand": "card_brand",
        "cardLast4": "card_last4",
        "failureCode": "failure_code",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
    }
    return {public: row[column] for public, column in mapping.items()}
