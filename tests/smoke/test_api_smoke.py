import os
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
    pet = {"id": str(uuid4()), "name": "Smoke Test Dog", "status": "available"}

    forbidden = client.post("/pet", json=pet, headers=bearer(user_token))
    assert_error(forbidden, 403, "FORBIDDEN")

    created = client.post("/pet", json=pet, headers=bearer(admin_token))
    assert created.status_code == 201, created.text
    assert created.json()["id"] == pet["id"]


def test_user_can_create_and_read_own_order(client: httpx.Client) -> None:
    token = login(client, "user1", "password123")
    pets = client.get("/pet/findByStatus", params={"status": "available"})
    assert pets.status_code == 200, pets.text
    pet_id = pets.json()[0]["id"]
    UUID(pet_id)
    created = client.post(
        "/store/order",
        json={"petId": pet_id, "quantity": 1, "status": "placed", "complete": False},
        headers=bearer(token),
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    UUID(order_id)

    fetched = client.get(f"/store/order/{order_id}", headers=bearer(token))
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == order_id


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
