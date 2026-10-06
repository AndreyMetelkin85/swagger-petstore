from unittest.mock import Mock
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from petstore.app import create_app
from petstore.config import Settings
from petstore.data.database import Database
from petstore.model import responses as response_models
from petstore.service.exceptions import ApiException


@pytest.fixture
def client():
    database = Mock(spec=Database)
    database.is_healthy.return_value = True
    app = create_app(database=database, start_database=False)
    with TestClient(app) as client:
        yield client


def test_every_openapi_operation_is_registered_once(client):
    app = client.app
    spec = yaml.safe_load((Settings().resources / "openapi.yaml").read_text(encoding="utf-8"))
    expected = {
        (method.upper(), "/api/v3" + path, operation["operationId"])
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in {"get", "post", "put", "delete", "patch"}
    }
    actual = {
        (method, route.path, route.name)
        for route in app.routes
        if hasattr(route, "methods")
        for method in route.methods
        if route.path not in {"/api/v3/openapi.json", "/api/v3/openapi.yaml"}
    }
    assert actual == expected
    assert len(expected) == 78


def test_original_schema_security_and_operation_ids_are_preserved(client):
    actual = client.get("/api/v3/openapi.json").json()
    original = yaml.safe_load((Settings().resources / "openapi.yaml").read_text(encoding="utf-8"))
    assert actual["paths"] == original["paths"]
    assert actual["components"] == original["components"]


@pytest.mark.parametrize(
    "name",
    [
        "User",
        "RegistrationResponse",
        "ConfirmationLinkResponse",
        "PasswordResetLinkResponse",
        "LoginResponse",
        "Pet",
        "DeliveryDetails",
        "Order",
        "Payment",
        "ErrorDetail",
        "ErrorResponse",
        "HealthResponse",
    ],
)
def test_named_python_response_models_have_the_original_public_fields(name):
    original = yaml.safe_load((Settings().resources / "openapi.yaml").read_text(encoding="utf-8"))
    model = getattr(response_models, name)
    assert set(model.model_json_schema(by_alias=True)["properties"]) == set(
        original["components"]["schemas"][name]["properties"]
    )


@pytest.mark.parametrize("content", [b"", b"null", b" "])
def test_missing_body_is_400_not_empty_object_validation(client, content):
    response = client.post(
        "/api/v3/auth/register", content=content, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json() == {
        "status": 400,
        "error": "BAD_REQUEST",
        "message": "Request body is required",
        "details": [],
    }


@pytest.mark.parametrize("content", [b"{", b"[]", b"false", b'{"password": []}', b"\xff"])
def test_malformed_body_is_400(client, content):
    response = client.post(
        "/api/v3/auth/register", content=content, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "BAD_REQUEST"


def test_empty_object_is_422_with_ordered_original_details(client):
    response = client.post("/api/v3/auth/register", json={})
    assert response.status_code == 422
    assert response.json()["details"] == [
        {"field": "username", "message": "Username is required"},
        {"field": "password", "message": "Password is required"},
        {"field": "email", "message": "Email is required"},
    ]


@pytest.mark.parametrize(
    "path,message",
    [
        ("/pet/bad", "Pet id must be a valid UUID"),
        ("/users/bad", "User id must be a valid UUID"),
        ("/store/order/bad", "Order id must be a valid UUID"),
        (f"/store/order/{uuid4()}/payments/bad", "Payment id must be a valid UUID"),
    ],
)
def test_invalid_path_uuid_keeps_400(client, path, message):
    response = client.get("/api/v3" + path)
    assert response.status_code == 400
    assert response.json()["message"] == message


@pytest.mark.parametrize(
    "path,code",
    [
        ("/auth/confirm/" + str(uuid4()), "INVALID_CONFIRMATION_LINK"),
        ("/auth/password/reset", "INVALID_RESET_LINK"),
    ],
)
def test_missing_confirmation_or_reset_code(client, path, code):
    response = (
        client.get("/api/v3" + path)
        if "confirm" in path
        else client.post("/api/v3" + path, json={"newPassword": "ValidPass123"})
    )
    assert response.status_code == 400
    assert response.json()["error"] == code


@pytest.mark.parametrize("key,code", [(None, "IDEMPOTENCY_KEY_REQUIRED"), ("bad", "INVALID_IDEMPOTENCY_KEY")])
def test_missing_or_invalid_idempotency_header(client, key, code):
    headers = {} if key is None else {"Idempotency-Key": key}
    response = client.post(f"/api/v3/store/order/{uuid4()}/payments", json={}, headers=headers)
    assert response.status_code == 400
    assert response.json()["error"] == code


def test_missing_bearer_does_not_touch_database(client):
    response = client.get("/api/v3/user/me")
    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"
    client.app.state.database.connect.assert_not_called()


def test_health_failure_is_503(client):
    client.app.state.database.is_healthy.return_value = False
    response = client.get("/api/v3/health")
    assert response.status_code == 503
    assert response.json()["database"] == "DOWN"


@pytest.mark.parametrize(
    "path,method,status,code",
    [
        ("/missing", "get", 404, "NOT_FOUND"),
        ("/health", "delete", 405, "METHOD_NOT_ALLOWED"),
        ("/user/login", "get", 404, "NOT_FOUND"),
    ],
)
def test_framework_errors_keep_public_envelope(client, path, method, status, code):
    response = client.request(method, "/api/v3" + path)
    assert response.status_code == status
    assert response.json()["error"] == code
    assert set(response.json()) == {"status", "error", "message", "details"}


def test_request_id_and_logs_do_not_include_query_code_or_password(client, caplog):
    caplog.set_level("INFO", logger="petstore")
    response = client.post(
        "/api/v3/auth/login?code=never-log-this-code",
        json={"email": "bad", "password": "never-log-this-password"},
        headers={"X-Request-ID": "test-request-id"},
    )
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert "never-log-this-code" not in caplog.text
    assert "never-log-this-password" not in caplog.text


def test_unknown_legacy_delete_is_404_not_static_file_405(client):
    assert client.delete("/api/v3/user/user1").status_code == 404
    assert client.delete("/api/v3/user/me").status_code == 405


def test_internal_errors_do_not_leak_database_exception(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("secret-db-password-and-request-values")

    monkeypatch.setattr(client.app.state.auth, "register", fail)
    response = client.post(
        "/api/v3/auth/register",
        json={"username": "valid-name", "email": "valid@example.com", "password": "ValidPass123"},
    )
    assert response.status_code == 500
    assert "secret-db-password" not in response.text
    assert response.json()["message"] == "An unexpected error occurred"


def test_unsupported_content_type_keeps_original_415_message(client):
    response = client.post("/api/v3/auth/register", content="{}", headers={"Content-Type": "text/plain"})
    assert response.status_code == 415
    assert response.json()["message"] == "Content-Type must be application/json"


def test_business_error_details_are_not_rewritten(client, monkeypatch):
    def fail(*args, **kwargs):
        raise ApiException(409, "USER_ALREADY_EXISTS", "A user with this username or email already exists")

    monkeypatch.setattr(client.app.state.auth, "register", fail)
    response = client.post(
        "/api/v3/auth/register",
        json={"username": "valid-name", "email": "valid@example.com", "password": "ValidPass123"},
    )
    assert response.json()["details"] == []
