"""Сериализация публичных ответов без утечки приватных данных."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import simplejson
from starlette.responses import Response

from petstore.data.database import Row


def json_default(value: Any) -> str:
    """Сериализует UUID и время UTC без изменения точности денежных сумм.

    :param value: Значение, проверяемое или преобразуемое текущей операцией.
    :return: Строковый результат описанной операции.
    """
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    raise TypeError(f"Unsupported response type: {type(value).__name__}")


class Responses(Response):
    """Действующий JSON-формат с точными Decimal и UTF-8."""

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        """Сериализует безопасный ответ без преобразования денежных сумм во float.

        :param content: Данные для сериализации в публичный ответ.
        :return: Содержимое результата в байтах.
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
    """Возвращает только публичные поля User без пароля и хешей ссылок.

    :param row: Строка базы данных для обработки или преобразования.
    :return: Результат операции типа Row.
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
        if address["apartment"] is None:
            del address["apartment"]
    result = {
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
    # Jackson пропускал необязательные контакты null, но сохранял явный address: null.
    return {
        key: value
        for key, value in result.items()
        if value is not None or key not in {"firstName", "lastName", "phone"}
    }


def public_delivery(snapshot: Row | None) -> Row | None:
    """Сохраняет действующий формат неизменяемого снимка доставки.

    :param snapshot: Сохранённый неизменяемый снимок данных оформления.
    :return: Результат операции типа Row | None.
    """
    if snapshot is None:
        return None
    result = dict(snapshot)
    address = result.get("address")
    if isinstance(address, dict) and cast(Row, address).get("apartment") is None:
        result["address"] = {name: value for name, value in cast(Row, address).items() if name != "apartment"}
    return result


def public_order(row: Row) -> Row:
    """Преобразует SQL-столбцы снимка в действующий контракт заказа.

    :param row: Строка базы данных для обработки или преобразования.
    :return: Результат операции типа Row.
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
    return {
        public: public_delivery(row[column]) if public == "deliveryDetails" else row[column]
        for public, column in mapping.items()
        if public != "shipDate" or row[column] is not None
    }


def public_payment(row: Row) -> Row:
    """Возвращает сводку платежа без хешей запросов и ключей идемпотентности.

    :param row: Строка базы данных для обработки или преобразования.
    :return: Результат операции типа Row.
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
    return {
        public: row[column]
        for public, column in mapping.items()
        if public != "failureCode" or row[column] is not None
    }
