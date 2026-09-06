import os
import base64
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4
from urllib.parse import urlsplit

import httpx
import pytest


BASE_URL = os.getenv("BASE_URL", "http://localhost:8080/api/v3")
DELIVERY_ADDRESS = {
    "city": "Москва",
    "street": "Федорова",
    "house": "30",
    "apartment": "12",
    "postalCode": "123456",
}
KNOWN_EMAILS = {
    "admin": "admin@example.com",
    "user1": "test@example.com",
}


def to_email(login: str) -> str:
    return KNOWN_EMAILS.get(login, login)


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as session:
        yield session


def login(client: httpx.Client, email_or_demo: str, password: str) -> str:
    email = to_email(email_or_demo) if "@" not in email_or_demo else email_or_demo
    response = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    UUID(body["user"]["id"])
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    return body["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_pet(client: httpx.Client, admin_token: str, prefix: str = "AQA") -> dict:
    response = client.post(
        "/pet",
        json={
            "name": f"{prefix} Pet {uuid4().hex[:8]}",
            "category": {"name": "Automated tests"},
            "tags": [{"name": "aqa"}],
            "photoUrls": [],
            "status": "available",
            "price": 15000.00,
        },
        headers=bearer(admin_token),
    )
    assert response.status_code == 201, response.text
    pet = response.json()
    UUID(pet["id"])
    assert pet["version"] == 0
    UUID(pet["category"]["id"])
    UUID(pet["tags"][0]["id"])
    return pet


def complete_profile(client: httpx.Client, token: str) -> dict:
    response = client.put(
        "/user/me",
        json={
            "firstName": "Test",
            "lastName": "User",
            "phone": "+7 999 123-45-67",
            "address": DELIVERY_ADDRESS,
        },
        headers=bearer(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["address"]["postalCode"] == "123456"
    return response.json()


def pay_order(client: httpx.Client, token: str, order_id: str,
              card_number: str = "4242424242424242", key: str | None = None) -> httpx.Response:
    return client.post(
        f"/store/order/{order_id}/payments",
        headers={**bearer(token), "Idempotency-Key": key or str(uuid4())},
        json={
            "cardNumber": card_number,
            "expiryMonth": 12,
            "expiryYear": 2099,
            "cvv": "123",
            "cardholderName": "IVAN IVANOV",
        },
    )


def api_path(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path
    prefix = "/api/v3"
    if path.startswith(prefix):
        path = path[len(prefix) :]
    return f"{path}?{parsed.query}" if parsed.query else path


def register_user(client: httpx.Client, prefix: str) -> tuple[dict, str, str, str]:
    suffix = uuid4().hex[:10]
    username = f"{prefix}{suffix}"
    email = f"{username}@example.test"
    password = "StartPass123"
    response = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    UUID(body["user"]["id"])
    assert body["user"]["userStatus"] == "PENDING"
    assert "password" not in body["user"]
    assert body["confirmationUrl"].startswith("http")
    return body, username, email, password


def assert_error(response: httpx.Response, status: int, error: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"status", "error", "message", "details"}
    assert body["status"] == status
    assert body["error"] == error
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["details"], list)


def legacy_admin_token() -> str:
    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    now = int(time.time())
    header = encode({"alg": "HS256", "typ": "JWT"})
    payload = encode(
        {"sub": "admin", "role": "ADMIN", "ver": 0, "iat": now, "exp": now + 300}
    )
    unsigned = f"{header}.{payload}"
    signature = hmac.new(
        b"local-petstore-secret-change-me", unsigned.encode(), hashlib.sha256
    ).digest()
    return f"{unsigned}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def test_public_health(client: httpx.Client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"


def test_private_endpoint_without_token_returns_401(client: httpx.Client) -> None:
    response = client.get("/user/me")
    assert_error(response, 401, "UNAUTHORIZED")
    assert response.json()["message"] == "Bearer token is required"


def test_invalid_token_returns_401(client: httpx.Client) -> None:
    response = client.get("/user/me", headers=bearer("not-a-valid-token"))
    assert_error(response, 401, "INVALID_TOKEN")


def test_legacy_public_secret_cannot_forge_admin_token(client: httpx.Client) -> None:
    response = client.get(
        "/store/inventory", headers=bearer(legacy_admin_token())
    )
    assert_error(response, 401, "INVALID_TOKEN")


def test_validation_error_contains_field_details(client: httpx.Client) -> None:
    response = client.post("/auth/register", json={})
    assert_error(response, 422, "VALIDATION_ERROR")
    details = response.json()["details"]
    assert details
    assert all(set(detail) == {"field", "message"} for detail in details)


def test_malformed_json_uses_public_error_contract(client: httpx.Client) -> None:
    response = client.post(
        "/auth/login",
        content="{",
        headers={"Content-Type": "application/json"},
    )
    assert_error(response, 400, "BAD_REQUEST")
    assert response.json()["message"] == (
        "Request body contains malformed or incompatible JSON"
    )


def test_missing_request_body_uses_public_error_contract(client: httpx.Client) -> None:
    response = client.post(
        "/auth/login",
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    assert_error(response, 400, "BAD_REQUEST")
    assert response.json()["message"] == "Request body is required"


def test_invalid_uuid_uses_endpoint_specific_error(client: httpx.Client) -> None:
    response = client.get("/pet/not-a-uuid")
    assert_error(response, 400, "BAD_REQUEST")
    assert response.json()["message"] == "Pet id must be a valid UUID"


def test_missing_required_query_uses_endpoint_specific_error(
    client: httpx.Client,
) -> None:
    response = client.get("/pet/findByStatus")
    assert_error(response, 400, "BAD_REQUEST")
    assert response.json()["message"] == "Status is required"


def test_user_me_updates_only_self_service_profile_fields(client: httpx.Client) -> None:
    user_token = login(client, "user1", "password123")
    profile = client.get("/user/me", headers=bearer(user_token)).json()
    original_email = profile["email"]

    for forbidden_body in (
        {"email": "hijacked@example.test"},
        {"password": "DoNotChange123"},
        {"currentPassword": "password123", "password": "DoNotChange123"},
        {"username": "changed-by-user"},
        {"role": "ADMIN"},
        {"userStatus": "BLOCKED"},
    ):
        blocked = client.put(
            "/user/me", json=forbidden_body, headers=bearer(user_token)
        )
        assert_error(blocked, 422, "VALIDATION_ERROR")

    first_name = f"Updated-{uuid4().hex[:8]}"
    updated = client.put(
        "/user/me", json={"firstName": first_name}, headers=bearer(user_token)
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["firstName"] == first_name
    refreshed = client.get("/user/me", headers=bearer(user_token)).json()
    assert refreshed["email"] == original_email


def test_role_based_user_management(client: httpx.Client) -> None:
    registration, username, email, password = register_user(client, "managed")
    confirmed = client.get(api_path(registration["confirmationUrl"]))
    assert confirmed.status_code == 200, confirmed.text
    user_id = registration["user"]["id"]
    user_token = login(client, email, password)
    admin_token = login(client, "admin", "admin123")

    listed = client.get("/users", headers=bearer(admin_token))
    assert listed.status_code == 200, listed.text
    assert user_id in {user["id"] for user in listed.json()}
    fetched = client.get(f"/users/{user_id}", headers=bearer(admin_token))
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["email"] == email

    update_body = {
        "username": f"managed_{uuid4().hex[:8]}",
        "firstName": "Managed",
        "lastName": "User",
        "email": f"managed-{uuid4().hex[:8]}@example.test",
        "phone": "+1-555-0199",
        "role": "USER",
        "address": DELIVERY_ADDRESS,
    }
    forbidden = client.put(
        f"/users/{user_id}", json=update_body, headers=bearer(user_token)
    )
    assert_error(forbidden, 403, "FORBIDDEN")

    password_update = dict(update_body, password="AdminMustNotSetPasswords123")
    rejected_password = client.put(
        f"/users/{user_id}", json=password_update, headers=bearer(admin_token)
    )
    assert_error(rejected_password, 422, "VALIDATION_ERROR")

    updated = client.put(
        f"/users/{user_id}",
        json=update_body,
        headers=bearer(admin_token),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["username"] == update_body["username"]
    assert updated.json()["email"] == update_body["email"]
    assert updated.json()["role"] == "USER"
    assert "password" not in updated.json()

    revoked = client.get("/user/me", headers=bearer(user_token))
    assert_error(revoked, 401, "INVALID_TOKEN")

    old_login = client.post("/auth/login", json={"email": email, "password": password})
    assert_error(old_login, 401, "INVALID_CREDENTIALS")
    updated_user_token = login(client, update_body["email"], password)

    promoted_body = dict(update_body, role="ADMIN")
    promoted = client.put(
        f"/users/{user_id}", json=promoted_body, headers=bearer(admin_token)
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "ADMIN"
    assert_error(
        client.get("/user/me", headers=bearer(updated_user_token)),
        401,
        "INVALID_TOKEN",
    )
    promoted_token = login(client, update_body["email"], password)
    assert client.get("/users", headers=bearer(promoted_token)).status_code == 200


def test_password_reset_validation_names_new_password_field(
    client: httpx.Client,
) -> None:
    response = client.post(
        f"/auth/password/reset/{uuid4()}?code=unused-test-code",
        json={"newPassword": "short"},
    )
    assert_error(response, 422, "VALIDATION_ERROR")
    assert response.json()["details"][0]["field"] == "newPassword"


def test_password_reset_clears_five_attempt_login_lock(client: httpx.Client) -> None:
    registration, _, email, password = register_user(client, "lock-reset")
    confirmed = client.get(api_path(registration["confirmationUrl"]))
    assert confirmed.status_code == 200, confirmed.text

    for _ in range(4):
        assert_error(
            client.post(
                "/auth/login", json={"email": email, "password": "WrongPass123"}
            ),
            401,
            "INVALID_CREDENTIALS",
        )
    fifth = client.post(
        "/auth/login", json={"email": email, "password": "WrongPass123"}
    )
    assert_error(fifth, 429, "LOGIN_RATE_LIMITED")
    resend_while_locked = client.post(
        "/auth/confirmation/resend", json={"email": email, "password": password}
    )
    assert_error(resend_while_locked, 429, "LOGIN_RATE_LIMITED")

    forgot = client.post("/auth/password/forgot", json={"email": email})
    assert forgot.status_code == 200, forgot.text
    new_password = "UnlockedByReset123"
    reset = client.post(
        api_path(forgot.json()["resetUrl"]), json={"newPassword": new_password}
    )
    assert reset.status_code == 204, reset.text
    login(client, email, new_password)


def test_user_cannot_create_pet_but_admin_can(client: httpx.Client) -> None:
    user_token = login(client, "user1", "password123")
    admin_token = login(client, "admin", "admin123")
    pet = {"name": "Smoke Test Dog", "status": "available", "price": 15000.00}

    forbidden = client.post("/pet", json=pet, headers=bearer(user_token))
    assert_error(forbidden, 403, "FORBIDDEN")

    created = client.post("/pet", json=pet, headers=bearer(admin_token))
    assert created.status_code == 201, created.text
    UUID(created.json()["id"])


def test_pet_create_and_update_models_have_separate_validation(
    client: httpx.Client,
) -> None:
    admin_token = login(client, "admin", "admin123")
    nested = client.post(
        "/pet",
        json={"name": "Invalid nested fields", "category": {}, "tags": [{}], "price": 15000.00},
        headers=bearer(admin_token),
    )
    assert_error(nested, 422, "VALIDATION_ERROR")
    fields = {detail["field"] for detail in nested.json()["details"]}
    assert {"category.name", "tags[0].name"}.issubset(fields)

    invalid_status = client.post(
        "/pet",
        json={"name": "Invalid status", "status": "unknown", "price": 15000.00},
        headers=bearer(admin_token),
    )
    assert_error(invalid_status, 422, "VALIDATION_ERROR")
    assert invalid_status.json()["details"][0]["field"] == "status"

    invalid_pet_id = client.put(
        "/pet/not-a-uuid",
        json={"version": 0, "name": "Invalid id"},
        headers=bearer(admin_token),
    )
    assert_error(invalid_pet_id, 400, "BAD_REQUEST")
    assert invalid_pet_id.json()["message"] == "Pet id must be a valid UUID"


def test_pet_update_uses_optimistic_lock(client: httpx.Client) -> None:
    admin_token = login(client, "admin", "admin123")
    pet = create_pet(client, admin_token, "Versioned")
    update = {
        "version": pet["version"],
        "name": f"{pet['name']} updated",
        "category": pet.get("category"),
        "photoUrls": pet.get("photoUrls", []),
        "tags": pet.get("tags", []),
        "status": pet["status"],
        "price": pet["price"],
    }

    first = client.put(f"/pet/{pet['id']}", json=update, headers=bearer(admin_token))
    assert first.status_code == 200, first.text
    assert first.json()["version"] == pet["version"] + 1

    stale = client.put(f"/pet/{pet['id']}", json=update, headers=bearer(admin_token))
    assert_error(stale, 409, "PET_VERSION_CONFLICT")


def test_user_can_create_and_read_own_order(client: httpx.Client) -> None:
    token = login(client, "user1", "password123")
    complete_profile(client, token)
    admin_token = login(client, "admin", "admin123")
    pet_id = create_pet(client, admin_token)["id"]
    created = client.post(
        "/store/order",
        json={"petId": pet_id, "quantity": 1},
        headers=bearer(token),
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    UUID(order_id)
    assert created.json()["status"] == "placed"
    assert created.json()["complete"] is False
    assert created.json().get("shipDate") is None

    reserved = client.get(f"/pet/{pet_id}")
    assert reserved.status_code == 200, reserved.text
    assert reserved.json()["status"] == "reserved"

    fetched = client.get(f"/store/order/{order_id}", headers=bearer(token))
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == order_id
    assert fetched.json()["currency"] == "RUB"
    assert fetched.json()["paymentStatus"] == "UNPAID"
    assert fetched.json()["deliveryDetails"]["address"]["postalCode"] == "123456"

    unpaid_approval = client.post(
        f"/store/order/{order_id}/approve", headers=bearer(admin_token)
    )
    assert_error(unpaid_approval, 409, "ORDER_NOT_PAID")


def test_order_reservation_is_atomic_and_cancellation_releases_pet(
    client: httpx.Client,
) -> None:
    token = login(client, "user1", "password123")
    complete_profile(client, token)
    admin_token = login(client, "admin", "admin123")
    pet_id = create_pet(client, admin_token, "Concurrent")["id"]

    def place_order(_: int) -> httpx.Response:
        return client.post(
            "/store/order",
            json={"petId": pet_id, "quantity": 1},
            headers=bearer(token),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(place_order, range(2)))
    assert sorted(response.status_code for response in results) == [201, 409]
    assert_error(
        next(response for response in results if response.status_code == 409),
        409,
        "PET_NOT_AVAILABLE",
    )

    order = next(response.json() for response in results if response.status_code == 201)
    cancelled = client.post(
        f"/store/order/{order['id']}/cancel", headers=bearer(token)
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["complete"] is True

    released = client.get(f"/pet/{pet_id}")
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "available"

    protected = client.delete(f"/pet/{pet_id}", headers=bearer(admin_token))
    assert_error(protected, 409, "PET_HAS_ORDERS")


def test_order_lifecycle_requires_admin_and_follows_state_machine(
    client: httpx.Client,
) -> None:
    token = login(client, "user1", "password123")
    complete_profile(client, token)
    admin_token = login(client, "admin", "admin123")
    pet_id = create_pet(client, admin_token, "Lifecycle")["id"]
    created = client.post(
        "/store/order",
        json={"petId": pet_id, "quantity": 1},
        headers=bearer(token),
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]

    forbidden = client.post(
        f"/store/order/{order_id}/approve", headers=bearer(token)
    )
    assert_error(forbidden, 403, "FORBIDDEN")

    paid = pay_order(client, token, order_id)
    assert paid.status_code == 201, paid.text
    assert paid.json()["status"] == "SUCCEEDED"

    approved = client.post(
        f"/store/order/{order_id}/approve", headers=bearer(admin_token)
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    repeated = client.post(
        f"/store/order/{order_id}/approve", headers=bearer(admin_token)
    )
    assert_error(repeated, 409, "INVALID_STATUS_TRANSITION")

    shipped = client.post(
        f"/store/order/{order_id}/ship", headers=bearer(admin_token)
    )
    assert shipped.status_code == 200, shipped.text
    assert shipped.json()["status"] == "shipped"
    assert shipped.json()["shipDate"] is not None

    delivered = client.post(
        f"/store/order/{order_id}/deliver", headers=bearer(admin_token)
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["status"] == "delivered"
    assert delivered.json()["complete"] is True

    sold = client.get(f"/pet/{pet_id}")
    assert sold.status_code == 200, sold.text
    assert sold.json()["status"] == "sold"

    too_late = client.post(
        f"/store/order/{order_id}/cancel", headers=bearer(token)
    )
    assert_error(too_late, 409, "INVALID_STATUS_TRANSITION")


def test_user_cannot_access_or_cancel_another_users_order(
    client: httpx.Client,
) -> None:
    user_token = login(client, "user1", "password123")
    admin_token = login(client, "admin", "admin123")
    complete_profile(client, user_token)
    complete_profile(client, admin_token)
    pet_id = create_pet(client, admin_token, "Ownership")["id"]
    created = client.post(
        "/store/order",
        json={"petId": pet_id, "quantity": 1},
        headers=bearer(admin_token),
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]

    forbidden_get = client.get(
        f"/store/order/{order_id}", headers=bearer(user_token)
    )
    assert_error(forbidden_get, 403, "ORDER_ACCESS_DENIED")

    forbidden_cancel = client.post(
        f"/store/order/{order_id}/cancel", headers=bearer(user_token)
    )
    assert_error(forbidden_cancel, 403, "ORDER_ACCESS_DENIED")

    cancelled = client.post(
        f"/store/order/{order_id}/cancel", headers=bearer(admin_token)
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"


def test_order_rejects_unknown_pet(client: httpx.Client) -> None:
    token = login(client, "user1", "password123")
    complete_profile(client, token)
    response = client.post(
        "/store/order",
        json={"petId": str(uuid4()), "quantity": 1},
        headers=bearer(token),
    )
    assert_error(response, 404, "PET_NOT_FOUND")


def test_order_rejects_server_managed_fields(client: httpx.Client) -> None:
    token = login(client, "user1", "password123")
    response = client.post(
        "/store/order",
        json={
            "petId": str(uuid4()),
            "quantity": 1,
            "status": "delivered",
            "complete": True,
        },
        headers=bearer(token),
    )
    assert_error(response, 422, "VALIDATION_ERROR")
    assert {detail["field"] for detail in response.json()["details"]} == {
        "status",
        "complete",
    }


def test_address_registration_validation_update_and_clear(
    client: httpx.Client,
) -> None:
    suffix = uuid4().hex[:10]
    email = f"address-{suffix}@example.test"
    response = client.post(
        "/auth/register",
        json={
            "username": f"address{suffix}",
            "email": email,
            "password": "AddressPass123",
            "firstName": "Иван",
            "lastName": "Иванов",
            "phone": "+7 999 123-45-67",
            "address": DELIVERY_ADDRESS,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["user"]["address"] == DELIVERY_ADDRESS
    assert client.get(api_path(response.json()["confirmationUrl"])).status_code == 200
    token = login(client, email, "AddressPass123")

    cleared = client.put(
        "/user/me", json={"address": None}, headers=bearer(token)
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["address"] is None

    leading_zero = dict(DELIVERY_ADDRESS, postalCode="012345")
    restored = client.put(
        "/user/me", json={"address": leading_zero}, headers=bearer(token)
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["address"]["postalCode"] == "012345"

    invalid = client.put(
        "/user/me",
        json={"address": {"city": "Москва", "postalCode": "12345"}},
        headers=bearer(token),
    )
    assert_error(invalid, 422, "VALIDATION_ERROR")
    assert {item["field"] for item in invalid.json()["details"]} >= {
        "address.street",
        "address.house",
        "address.postalCode",
    }


def test_order_requires_profile_and_keeps_delivery_and_price_snapshot(
    client: httpx.Client,
) -> None:
    registration, _, email, password = register_user(client, "checkout")
    assert client.get(api_path(registration["confirmationUrl"])).status_code == 200
    token = login(client, email, password)
    admin_token = login(client, "admin", "admin123")
    pet = create_pet(client, admin_token, "Snapshot")

    incomplete = client.post(
        "/store/order",
        json={"petId": pet["id"], "quantity": 1},
        headers=bearer(token),
    )
    assert_error(incomplete, 409, "PROFILE_INCOMPLETE")
    missing = {item["field"] for item in incomplete.json()["details"]}
    assert {"firstName", "lastName", "phone", "address.city", "address.postalCode"} <= missing

    profile = complete_profile(client, token)
    created = client.post(
        "/store/order",
        json={"petId": pet["id"], "quantity": 1},
        headers=bearer(token),
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert float(order["unitPrice"]) == 15000.0
    assert order["deliveryDetails"]["address"] == profile["address"]

    changed_address = dict(DELIVERY_ADDRESS, city="Казань", postalCode="420000")
    assert client.put(
        "/user/me", json={"address": changed_address}, headers=bearer(token)
    ).status_code == 200
    pet_update = {
        "version": client.get(f"/pet/{pet['id']}").json()["version"],
        "name": pet["name"],
        "category": pet.get("category"),
        "photoUrls": pet.get("photoUrls", []),
        "tags": pet.get("tags", []),
        "price": 19999.99,
    }
    changed_pet = client.put(
        f"/pet/{pet['id']}", json=pet_update, headers=bearer(admin_token)
    )
    assert changed_pet.status_code == 200, changed_pet.text

    stored = client.get(
        f"/store/order/{order['id']}", headers=bearer(token)
    ).json()
    assert float(stored["unitPrice"]) == 15000.0
    assert stored["deliveryDetails"]["address"]["city"] == "Москва"


def test_payment_success_idempotency_history_and_paid_cancellation(
    client: httpx.Client,
) -> None:
    token = login(client, "user1", "password123")
    complete_profile(client, token)
    admin_token = login(client, "admin", "admin123")
    pet = create_pet(client, admin_token, "Payment")
    order = client.post(
        "/store/order",
        json={"petId": pet["id"], "quantity": 1},
        headers=bearer(token),
    ).json()

    key = str(uuid4())
    paid = pay_order(client, token, order["id"], key=key)
    assert paid.status_code == 201, paid.text
    payment = paid.json()
    assert payment["status"] == "SUCCEEDED"
    assert payment["cardLast4"] == "4242"
    assert "cardNumber" not in payment and "cvv" not in payment

    replay = pay_order(client, token, order["id"], key=key)
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == payment["id"]

    conflict = pay_order(
        client, token, order["id"], card_number="4000000000000002", key=key
    )
    assert_error(conflict, 409, "IDEMPOTENCY_KEY_REUSED")

    history = client.get(
        f"/store/order/{order['id']}/payments", headers=bearer(token)
    )
    assert history.status_code == 200, history.text
    assert payment["id"] in {item["id"] for item in history.json()}
    fetched = client.get(
        f"/store/order/{order['id']}/payments/{payment['id']}",
        headers=bearer(token),
    )
    assert fetched.status_code == 200, fetched.text

    duplicate = pay_order(client, token, order["id"])
    assert_error(duplicate, 409, "ORDER_ALREADY_PAID")

    cancelled = client.post(
        f"/store/order/{order['id']}/cancel", headers=bearer(token)
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["paymentStatus"] == "REFUNDED"
    refunded = client.get(
        f"/store/order/{order['id']}/payments/{payment['id']}",
        headers=bearer(token),
    ).json()
    assert refunded["status"] == "REFUNDED"
    assert client.get(f"/pet/{pet['id']}").json()["status"] == "available"


@pytest.mark.parametrize(
    ("card_number", "error"),
    [
        ("4000000000000002", "PAYMENT_DECLINED"),
        ("4000000000009995", "INSUFFICIENT_FUNDS"),
    ],
)
def test_declined_payment_can_be_retried(
    client: httpx.Client, card_number: str, error: str
) -> None:
    token = login(client, "user1", "password123")
    complete_profile(client, token)
    admin_token = login(client, "admin", "admin123")
    pet = create_pet(client, admin_token, "Decline")
    order = client.post(
        "/store/order",
        json={"petId": pet["id"], "quantity": 1},
        headers=bearer(token),
    ).json()

    declined = pay_order(client, token, order["id"], card_number=card_number)
    assert_error(declined, 402, error)
    assert client.get(
        f"/store/order/{order['id']}", headers=bearer(token)
    ).json()["paymentStatus"] == "UNPAID"

    retry = pay_order(client, token, order["id"])
    assert retry.status_code == 201, retry.text


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"cardNumber": "4242424242424241"},
        {"expiryMonth": 1, "expiryYear": 2020},
        {"cvv": "12"},
    ],
)
def test_invalid_payment_details_return_validation_error(
    client: httpx.Client, invalid_fields: dict
) -> None:
    token = login(client, "user1", "password123")
    complete_profile(client, token)
    admin_token = login(client, "admin", "admin123")
    pet = create_pet(client, admin_token, "Invalid payment")
    order_response = client.post(
        "/store/order",
        json={"petId": pet["id"], "quantity": 1},
        headers=bearer(token),
    )
    assert order_response.status_code == 201, order_response.text
    order = order_response.json()

    payload = {
        "cardNumber": "4242424242424242",
        "expiryMonth": 12,
        "expiryYear": 2099,
        "cvv": "123",
        "cardholderName": "IVAN IVANOV",
    }
    payload.update(invalid_fields)
    response = client.post(
        f"/store/order/{order['id']}/payments",
        headers={**bearer(token), "Idempotency-Key": str(uuid4())},
        json=payload,
    )
    assert_error(response, 422, "VALIDATION_ERROR")
    assert client.get(
        f"/store/order/{order['id']}", headers=bearer(token)
    ).json()["paymentStatus"] == "UNPAID"


def test_address_country_is_managed_by_server(client: httpx.Client) -> None:
    username = f"addresscountry{uuid4().hex[:10]}"
    response = client.post(
        "/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.test",
            "password": "StartPass123",
            "address": {**DELIVERY_ADDRESS, "country": "RU"},
        },
    )
    assert_error(response, 422, "VALIDATION_ERROR")
    assert "address.country" in {item["field"] for item in response.json()["details"]}


def test_parallel_payment_and_payment_ownership(client: httpx.Client) -> None:
    user_token = login(client, "user1", "password123")
    admin_token = login(client, "admin", "admin123")
    complete_profile(client, user_token)
    complete_profile(client, admin_token)
    pet = create_pet(client, admin_token, "Parallel payment")
    order = client.post(
        "/store/order",
        json={"petId": pet["id"], "quantity": 1},
        headers=bearer(admin_token),
    ).json()

    forbidden = pay_order(client, user_token, order["id"])
    assert_error(forbidden, 403, "ORDER_ACCESS_DENIED")

    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: pay_order(client, admin_token, order["id"], key=key), range(2))
        )
    assert sorted(response.status_code for response in results) == [200, 201]
    assert len({response.json()["id"] for response in results}) == 1


def test_destructive_user_and_order_operations_are_not_available(
    client: httpx.Client,
) -> None:
    user_token = login(client, "user1", "password123")
    admin_token = login(client, "admin", "admin123")

    assert client.delete("/user/me", headers=bearer(user_token)).status_code == 405
    assert client.delete("/user/user1", headers=bearer(admin_token)).status_code == 404
    assert (
        client.delete(f"/store/order/{uuid4()}", headers=bearer(admin_token)).status_code
        == 405
    )


def test_registration_confirmation_resend_and_unique_email(client: httpx.Client) -> None:
    registration, username, email, password = register_user(client, "confirm")

    pending_login = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert_error(pending_login, 403, "ACCOUNT_NOT_VERIFIED")

    resent = client.post(
        "/auth/confirmation/resend",
        json={"email": email, "password": password},
    )
    assert resent.status_code == 200, resent.text
    new_confirmation_url = resent.json()["confirmationUrl"]

    old_link = client.get(api_path(registration["confirmationUrl"]))
    assert_error(old_link, 400, "INVALID_CONFIRMATION_LINK")

    confirmed = client.get(api_path(new_confirmation_url))
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["userStatus"] == "ACTIVE"

    repeated = client.get(api_path(new_confirmation_url))
    assert_error(repeated, 409, "ACCOUNT_ALREADY_CONFIRMED")

    resend_active = client.post(
        "/auth/confirmation/resend",
        json={"email": email, "password": password},
    )
    assert_error(resend_active, 409, "ACCOUNT_ALREADY_CONFIRMED")

    duplicate_email = client.post(
        "/auth/register",
        json={
            "username": f"other{uuid4().hex[:10]}",
            "email": email.upper(),
            "password": password,
        },
    )
    assert_error(duplicate_email, 409, "USER_ALREADY_EXISTS")


def test_password_recovery_revokes_tokens(client: httpx.Client) -> None:
    registration, username, email, password = register_user(client, "recovery")
    confirmed = client.get(api_path(registration["confirmationUrl"]))
    assert confirmed.status_code == 200, confirmed.text
    old_token = login(client, email, password)

    missing = client.post(
        "/auth/password/forgot", json={"email": f"missing-{uuid4()}@example.test"}
    )
    assert_error(missing, 404, "USER_NOT_FOUND")

    forgot = client.post("/auth/password/forgot", json={"email": email})
    assert forgot.status_code == 200, forgot.text
    reset_url = forgot.json()["resetUrl"]
    new_password = "NewSecurePass456"

    reset = client.post(api_path(reset_url), json={"newPassword": new_password})
    assert reset.status_code == 204, reset.text

    repeated = client.post(api_path(reset_url), json={"newPassword": "AnotherPass789"})
    assert_error(repeated, 409, "RESET_LINK_ALREADY_USED")

    revoked = client.get("/user/me", headers=bearer(old_token))
    assert_error(revoked, 401, "INVALID_TOKEN")

    old_password = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert_error(old_password, 401, "INVALID_CREDENTIALS")
    login(client, email, new_password)


def test_admin_block_unblock_and_pending_confirmation(client: httpx.Client) -> None:
    registration, username, email, password = register_user(client, "blocked")
    user_id = registration["user"]["id"]
    admin_token = login(client, "admin", "admin123")

    blocked = client.post(
        f"/admin/users/{user_id}/block", headers=bearer(admin_token)
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["userStatus"] == "BLOCKED"

    repeated_block = client.post(
        f"/admin/users/{user_id}/block", headers=bearer(admin_token)
    )
    assert_error(repeated_block, 409, "INVALID_STATUS_TRANSITION")

    confirmed = client.get(api_path(registration["confirmationUrl"]))
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["userStatus"] == "BLOCKED"

    blocked_login = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert_error(blocked_login, 403, "ACCOUNT_BLOCKED")

    unblocked = client.post(
        f"/admin/users/{user_id}/unblock", headers=bearer(admin_token)
    )
    assert unblocked.status_code == 200, unblocked.text
    assert unblocked.json()["userStatus"] == "ACTIVE"

    repeated_unblock = client.post(
        f"/admin/users/{user_id}/unblock", headers=bearer(admin_token)
    )
    assert_error(repeated_unblock, 409, "INVALID_STATUS_TRANSITION")

    user_token = login(client, email, password)
    blocked_again = client.post(
        f"/admin/users/{user_id}/block", headers=bearer(admin_token)
    )
    assert blocked_again.status_code == 200, blocked_again.text
    while_blocked = client.get("/user/me", headers=bearer(user_token))
    assert_error(while_blocked, 403, "ACCOUNT_BLOCKED")

    restored = client.post(
        f"/admin/users/{user_id}/unblock", headers=bearer(admin_token)
    )
    assert restored.status_code == 200, restored.text
    still_revoked = client.get("/user/me", headers=bearer(user_token))
    assert_error(still_revoked, 401, "INVALID_TOKEN")
    login(client, email, password)


def test_account_state_transitions_are_atomic(client: httpx.Client) -> None:
    registration, username, email, _ = register_user(client, "atomic")
    confirmation_path = api_path(registration["confirmationUrl"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        confirmations = list(pool.map(lambda _: client.get(confirmation_path), range(2)))
    assert sorted(response.status_code for response in confirmations) == [200, 409]
    assert_error(
        next(response for response in confirmations if response.status_code == 409),
        409,
        "ACCOUNT_ALREADY_CONFIRMED",
    )

    forgot = client.post("/auth/password/forgot", json={"email": email})
    assert forgot.status_code == 200, forgot.text
    reset_path = api_path(forgot.json()["resetUrl"])
    passwords = ["AtomicPass123", "AtomicPass456"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        resets = list(
            pool.map(
                lambda password: client.post(
                    reset_path, json={"newPassword": password}
                ),
                passwords,
            )
        )
    assert sorted(response.status_code for response in resets) == [204, 409]
    assert_error(
        next(response for response in resets if response.status_code == 409),
        409,
        "RESET_LINK_ALREADY_USED",
    )
    winning_password = passwords[
        next(index for index, response in enumerate(resets) if response.status_code == 204)
    ]
    login(client, email, winning_password)

    admin_token = login(client, "admin", "admin123")
    user_id = registration["user"]["id"]
    block_path = f"/admin/users/{user_id}/block"
    with ThreadPoolExecutor(max_workers=2) as pool:
        blocks = list(
            pool.map(
                lambda _: client.post(block_path, headers=bearer(admin_token)), range(2)
            )
        )
    assert sorted(response.status_code for response in blocks) == [200, 409]
    assert_error(
        next(response for response in blocks if response.status_code == 409),
        409,
        "INVALID_STATUS_TRANSITION",
    )

    unblock_path = f"/admin/users/{user_id}/unblock"
    with ThreadPoolExecutor(max_workers=2) as pool:
        unblocks = list(
            pool.map(
                lambda _: client.post(unblock_path, headers=bearer(admin_token)), range(2)
            )
        )
    assert sorted(response.status_code for response in unblocks) == [200, 409]
    assert_error(
        next(response for response in unblocks if response.status_code == 409),
        409,
        "INVALID_STATUS_TRANSITION",
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/user"),
        ("GET", "/user/login?username=user1&password=password123"),
        ("GET", "/user/logout"),
        ("POST", "/user/createWithList"),
        ("POST", "/pet/4/uploadImage"),
        ("POST", "/pet/4"),
        ("PUT", "/user/user1"),
    ],
)
def test_legacy_endpoint_is_not_available(
    client: httpx.Client, method: str, path: str
) -> None:
    response = client.request(method, path)
    assert response.status_code >= 400, response.text
    if response.headers.get("content-type", "").startswith("application/json"):
        assert "access_token" not in response.json()
