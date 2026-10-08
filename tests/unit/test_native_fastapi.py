import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from petstore.api import health
from petstore.api.dependencies import ContractRoute
from petstore.app import create_app
from petstore.data.database import Database
from petstore.model.requests import RegisterRequest
from petstore.model.responses import HealthResponse, Payment, User
from petstore.utils.responses import Responses


@pytest.fixture
def client():
    """Предоставляет HTTP-клиент текущего изолированного сценария.

    :return: Результат описанной проверки или подготовки тестовых данных.
    """
    database = Mock(spec=Database)
    database.is_healthy.return_value = True
    with TestClient(create_app(database=database, start_database=False)) as client:
        yield client


def test_all_operations_have_native_dependencies_and_response_validation(client):
    document = client.app.state.document
    operations = {
        o["operationId"]: o
        for item in document["paths"].values()
        for o in item.values()
        if isinstance(o, dict) and "operationId" in o
    }
    checked = []
    for context in iter_route_contexts(client.app.routes):
        route = context.original_route
        if not isinstance(route, APIRoute) or route.operation_id not in operations:
            continue
        operation = operations[route.operation_id]
        assert isinstance(route, ContractRoute)
        assert route.dependant.dependencies
        if "application/json" in operation.get("requestBody", {}).get("content", {}):
            assert route.body_field is not None
        json_response = any(
            "application/json" in value.get("content", {})
            for status, value in operation["responses"].items()
            if int(status) < 400
        )
        assert (route.response_field is not None) == json_response
        assert route.response_model_exclude_unset
        checked.append(route.operation_id)
    assert len(checked) == len(set(checked)) == 78


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "UP", "service": "swagger-petstore", "database": "UP"},
        {"status": "UP", "service": "swagger-petstore", "database": "UP", "timestamp": "not-a-date"},
        {
            "status": "UP",
            "service": "swagger-petstore",
            "database": "UP",
            "timestamp": "2026-10-07T00:00:00Z",
            "private": "never-leak-me",
        },
    ],
)
def test_bad_response_dtos_fail_closed_without_leaking_data(client, monkeypatch, payload):
    monkeypatch.setattr(client.app.state.controllers.health, "health", lambda context: Responses(payload))
    response = client.get("/api/v3/health")
    assert response.status_code == 500
    assert response.json()["error"] == "INTERNAL_SERVER_ERROR"
    assert "never-leak-me" not in response.text


def test_native_dependency_override_does_not_need_global_patching(client):
    controller = Mock()
    controller.health.return_value = Responses(
        {
            "status": "UP",
            "service": "injected",
            "database": "UP",
            "timestamp": datetime(2026, 10, 7, tzinfo=UTC),
        }
    )
    client.app.dependency_overrides[health.get_controller] = lambda: controller
    response = client.get("/api/v3/health")
    assert response.status_code == 200
    assert response.json()["service"] == "injected"
    assert response.json()["timestamp"] == "2026-10-07T00:00:00.000Z"
    controller.health.assert_called_once()


def test_python_constructor_keeps_snake_case_but_http_binding_is_alias_only():
    model = RegisterRequest(first_name="Python")
    assert model.first_name == "Python"
    wire = RegisterRequest.from_wire({"first_name": "not-an-http-field", "firstName": "HTTP"})
    assert wire.first_name == "HTTP"
    assert wire.model_extra == {"first_name": "not-an-http-field"}


def test_nested_private_response_fields_are_rejected():
    payload = {
        "id": uuid4(),
        "username": "buyer",
        "email": "buyer@example.com",
        "userStatus": "ACTIVE",
        "role": "USER",
        "address": {
            "city": "Москва",
            "street": "Тестовая",
            "house": "1",
            "postalCode": "123456",
            "password": "private",
        },
    }
    with pytest.raises(ValueError):
        User.model_validate(payload)


@pytest.mark.parametrize("path", ["/store/order/{id}/payments", "/store/orders/{id}/payments"])
def test_reused_payment_request_keeps_legacy_incompatible_json_error(client, path):
    response = client.post(
        "/api/v3" + path.format(id=uuid4()),
        json={"cardNumber": []},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "BAD_REQUEST"


@pytest.mark.parametrize(
    "method,path,headers,code,message",
    [
        ("POST", "/auth/password/reset", {}, "INVALID_RESET_LINK", "The one-time link is invalid"),
        ("PUT", "/pet/bad", {}, "BAD_REQUEST", "Pet id must be a valid UUID"),
        ("POST", "/store/orders", {}, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required"),
        (
            "POST",
            "/store/orders",
            {"Idempotency-Key": "bad"},
            "INVALID_IDEMPOTENCY_KEY",
            "Idempotency-Key must be a valid UUID",
        ),
    ],
)
@pytest.mark.parametrize(
    "body", [b"", b"{", b"x" * (1024 * 1024 + 1)], ids=["missing", "malformed", "oversized"]
)
def test_parameter_errors_keep_priority_over_missing_malformed_or_oversized_body(
    client, method, path, headers, code, message, body
):
    response = client.request(method, "/api/v3" + path, headers=headers, content=body)
    assert response.status_code == 400
    assert response.json()["error"] == code
    assert response.json()["message"] == message
    client.app.state.database.connect.assert_not_called()


@pytest.mark.parametrize("amount", ["0.01", "10.25", "999999999999.99"])
def test_response_money_stays_numeric_and_preserves_allowed_cent_precision(amount):
    model = Payment(
        id=uuid4(),
        order_id=uuid4(),
        amount=Decimal(amount),
        currency="RUB",
        status="SUCCEEDED",
        card_brand="VISA",
        card_last4="1111",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    result = json.loads(model.model_dump_json(by_alias=True), parse_float=Decimal)
    assert result["amount"] == Decimal(amount)
    assert not isinstance(result["amount"], str)
    assert "failureCode" not in model.model_dump(exclude_unset=True, by_alias=True)


def test_response_timestamp_keeps_legacy_utc_milliseconds():
    model = HealthResponse(
        status="UP",
        service="swagger-petstore",
        database="UP",
        timestamp=datetime(2026, 10, 7, 12, 34, 56, 123456, tzinfo=UTC),
    )
    assert json.loads(model.model_dump_json())["timestamp"] == "2026-10-07T12:34:56.123Z"
