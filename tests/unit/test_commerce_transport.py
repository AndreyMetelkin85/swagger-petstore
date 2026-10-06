from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from petstore.app import create_app
from petstore.data.database import Database
from petstore.service.media_service import MAX_BYTES


@pytest.fixture
def client():
    app = create_app(database=Mock(spec=Database), start_database=False)
    app.state.auth.authorize = Mock(return_value={"id": uuid4(), "role": "ADMIN"})
    with TestClient(app) as client:
        yield client


def test_commerce_validation_details_are_bounded_and_never_echo_secrets(client, caplog):
    secret = "PrivateSecretMustNotAppear"
    response = client.put(
        "/api/v3/store/cart",
        json={
            "version": 1,
            "lines": [{"kind": secret, "id": secret, "quantity": 0}] * 100,
        },
        headers={"X-Request-ID": "commerce-validation"},
    )
    assert response.status_code == 422
    assert len(response.json()["details"]) == 100
    assert secret not in response.text and secret not in caplog.text
    assert response.headers["X-Request-ID"] == "commerce-validation"


@pytest.mark.parametrize(
    "payload", [b"", b"null", b"{}", b"{", b"[]"], ids=["missing", "null", "empty", "malformed", "array"]
)
def test_new_commands_keep_missing_and_invalid_body_distinction(client, payload):
    response = client.post("/api/v3/products", content=payload, headers={"Content-Type": "application/json"})
    assert response.status_code == (422 if payload == b"{}" else 400)


def test_media_requires_multipart_and_a_single_supported_file_field(client):
    assert client.post("/api/v3/media", json={}).status_code == 415
    assert client.post("/api/v3/media", data={"sourceType": "OWN"}).status_code == 415
    response = client.post("/api/v3/media", files={"unexpected": ("x.png", b"x")})
    assert response.status_code == 422 and response.json()["error"] == "VALIDATION_ERROR"
    response = client.post("/api/v3/media", files={"sourceNote": ("x.txt", b"x")})
    assert response.status_code == 422 and response.json()["error"] == "INVALID_IMAGE"


def test_multipart_repeated_metadata_and_multiple_files_are_rejected(client):
    response = client.post(
        "/api/v3/media",
        files=[
            ("file", ("x.png", b"x")),
            ("sourceType", (None, "OWN")),
            ("sourceType", (None, "DEMO")),
        ],
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v3/media",
        files=[
            ("file", ("a.png", b"x")),
            ("file", ("b.png", b"x")),
        ],
    )
    assert response.status_code == 422 and response.json()["error"] == "INVALID_IMAGE"


def test_complete_upload_body_is_bounded_before_parsing(client):
    response = client.post(
        "/api/v3/media",
        content=b"a" * (MAX_BYTES + 65537),
        headers={"Content-Type": "multipart/form-data; boundary=test"},
    )
    assert response.status_code == 413 and response.json()["error"] == "IMAGE_TOO_LARGE"


def test_telemetry_allows_only_operational_events_and_limits_batches(client, caplog):
    caplog.set_level("INFO")
    valid = {"events": [{"event": "api_failure", "method": "GET", "httpStatus": 503, "durationMs": 2}]}
    assert client.post("/api/v3/telemetry/client-events", json=valid).status_code == 204
    assert "client_events count=1" in caplog.text
    assert (
        client.post("/api/v3/telemetry/client-events", json={"events": [{"event": "anything"}]}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v3/telemetry/client-events",
            json={"events": [{"event": "api_failure", "email": "not-logged@example.com"}]},
        ).status_code
        == 422
    )
    for _ in range(99):
        assert client.post("/api/v3/telemetry/client-events", json=valid).status_code == 204
    limited = client.post("/api/v3/telemetry/client-events", json=valid)
    assert limited.status_code == 429 and limited.json()["error"] == "TELEMETRY_RATE_LIMITED"
    assert "not-logged@example.com" not in caplog.text


def test_new_checkout_requires_valid_idempotency_key(client):
    response = client.post("/api/v3/store/orders", json={"cartVersion": 1})
    assert response.status_code == 400 and response.json()["error"] == "IDEMPOTENCY_KEY_REQUIRED"
    response = client.post(
        "/api/v3/store/orders", json={"cartVersion": 1}, headers={"Idempotency-Key": "bad"}
    )
    assert response.status_code == 400 and response.json()["error"] == "INVALID_IDEMPOTENCY_KEY"


def test_swagger_errors_and_required_versions_match_their_domain(client):
    spec = client.get("/api/v3/openapi.json").json()
    for path, item in spec["paths"].items():
        for operation in item.values():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            codes = {
                code
                for response in operation["responses"].values()
                for code in response.get("content", {}).get("application/json", {}).get("examples", {})
            }
            if path.startswith("/admin/pets"):
                assert not codes & {
                    "SKU_ALREADY_EXISTS",
                    "PRODUCT_VERSION_CONFLICT",
                    "STOCK_ADJUSTMENT_REQUIRED",
                }
            if path.startswith(
                ("/media", "/store/orders", "/catalog/categories", "/admin/catalog/categories", "/telemetry")
            ):
                assert "PRODUCT_VERSION_CONFLICT" not in codes
    for path in ("/products/{id}", "/admin/pets/{id}", "/admin/catalog/categories/{id}"):
        schema = spec["paths"][path]["put"]["requestBody"]["content"]["application/json"]["schema"]
        assert "version" in schema["allOf"][1]["required"]
    assert "200" not in spec["paths"]["/media"]["post"]["responses"]
    assert "200" in spec["paths"]["/store/orders"]["post"]["responses"]
    for path in ("/media/{id}", "/media/{id}/image", "/media/{id}/thumb"):
        security = spec["paths"][path]["get"]["security"]
        assert {} in security and {"bearerAuth": []} in security


def test_unknown_field_names_still_fit_the_public_error_contract(client):
    response = client.post("/api/v3/products", json={"sku": "TEST", "name": "Test", "price": 1, "q" * 200: 1})
    assert response.status_code == 422
    assert all(1 <= len(error["field"]) <= 100 for error in response.json()["details"])
