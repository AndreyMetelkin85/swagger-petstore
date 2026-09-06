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


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as session:
        yield session


def login(client: httpx.Client, username: str, password: str) -> str:
    response = client.post(
        "/auth/login", json={"username": username, "password": password}
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


def test_password_reset_validation_names_new_password_field(
    client: httpx.Client,
) -> None:
    response = client.post(
        f"/auth/password/reset/{uuid4()}?code=unused-test-code",
        json={"newPassword": "short"},
    )
    assert_error(response, 422, "VALIDATION_ERROR")
    assert response.json()["details"][0]["field"] == "newPassword"


def test_user_cannot_create_pet_but_admin_can(client: httpx.Client) -> None:
    user_token = login(client, "user1", "password123")
    admin_token = login(client, "admin", "admin123")
    pet = {"name": "Smoke Test Dog", "status": "available"}

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
        json={"name": "Invalid nested fields", "category": {}, "tags": [{}]},
        headers=bearer(admin_token),
    )
    assert_error(nested, 422, "VALIDATION_ERROR")
    fields = {detail["field"] for detail in nested.json()["details"]}
    assert {"category.name", "tags[0].name"}.issubset(fields)

    invalid_status = client.post(
        "/pet",
        json={"name": "Invalid status", "status": "unknown"},
        headers=bearer(admin_token),
    )
    assert_error(invalid_status, 422, "VALIDATION_ERROR")
    assert invalid_status.json()["details"][0]["field"] == "status"

    missing_id = client.put(
        "/pet",
        json={"name": "Missing id"},
        headers=bearer(admin_token),
    )
    assert_error(missing_id, 422, "VALIDATION_ERROR")
    assert "id" in {detail["field"] for detail in missing_id.json()["details"]}


def test_pet_update_uses_optimistic_lock(client: httpx.Client) -> None:
    admin_token = login(client, "admin", "admin123")
    pet = create_pet(client, admin_token, "Versioned")
    update = {
        "id": pet["id"],
        "version": pet["version"],
        "name": f"{pet['name']} updated",
        "category": pet.get("category"),
        "photoUrls": pet.get("photoUrls", []),
        "tags": pet.get("tags", []),
        "status": pet["status"],
    }

    first = client.put("/pet", json=update, headers=bearer(admin_token))
    assert first.status_code == 200, first.text
    assert first.json()["version"] == pet["version"] + 1

    stale = client.put("/pet", json=update, headers=bearer(admin_token))
    assert_error(stale, 409, "PET_VERSION_CONFLICT")


def test_user_can_create_and_read_own_order(client: httpx.Client) -> None:
    token = login(client, "user1", "password123")
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


def test_order_reservation_is_atomic_and_cancellation_releases_pet(
    client: httpx.Client,
) -> None:
    token = login(client, "user1", "password123")
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


def test_destructive_user_and_order_operations_are_not_available(
    client: httpx.Client,
) -> None:
    user_token = login(client, "user1", "password123")
    admin_token = login(client, "admin", "admin123")

    assert client.delete("/user/me", headers=bearer(user_token)).status_code == 405
    assert client.delete("/user/user1", headers=bearer(admin_token)).status_code == 405
    assert (
        client.delete(f"/store/order/{uuid4()}", headers=bearer(admin_token)).status_code
        == 405
    )


def test_registration_confirmation_resend_and_unique_email(client: httpx.Client) -> None:
    registration, username, email, password = register_user(client, "confirm")

    pending_login = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert_error(pending_login, 403, "ACCOUNT_NOT_VERIFIED")

    resent = client.post(
        "/auth/confirmation/resend",
        json={"username": username, "password": password},
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
        json={"username": username, "password": password},
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
    old_token = login(client, username, password)

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
        "/auth/login", json={"username": username, "password": password}
    )
    assert_error(old_password, 401, "INVALID_CREDENTIALS")
    login(client, username, new_password)


def test_admin_block_unblock_and_pending_confirmation(client: httpx.Client) -> None:
    registration, username, _, password = register_user(client, "blocked")
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
        "/auth/login", json={"username": username, "password": password}
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

    user_token = login(client, username, password)
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
    login(client, username, password)


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
    login(client, username, winning_password)

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
