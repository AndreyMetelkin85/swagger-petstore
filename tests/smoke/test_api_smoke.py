import os

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
    assert body["tokenType"] == "Bearer"
    assert body["expiresIn"] == 3600
    return body["accessToken"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_public_health(client: httpx.Client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"


def test_private_endpoint_without_token_returns_401(client: httpx.Client) -> None:
    response = client.get("/user/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_invalid_token_returns_401(client: httpx.Client) -> None:
    response = client.get("/user/me", headers=bearer("not-a-valid-token"))
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


def test_user_cannot_create_pet_but_admin_can(client: httpx.Client) -> None:
    user_token = login(client, "user1", "password123")
    admin_token = login(client, "admin", "admin123")
    pet = {"id": 900001, "name": "Smoke Test Dog", "status": "available"}

    forbidden = client.post("/pet", json=pet, headers=bearer(user_token))
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"

    created = client.post("/pet", json=pet, headers=bearer(admin_token))
    assert created.status_code == 201, created.text
    assert created.json()["id"] == pet["id"]

    deleted = client.delete(f"/pet/{pet['id']}", headers=bearer(admin_token))
    assert deleted.status_code == 204, deleted.text


def test_user_can_create_and_read_own_order(client: httpx.Client) -> None:
    token = login(client, "user1", "password123")
    created = client.post(
        "/store/order",
        json={"petId": 4, "quantity": 1, "status": "placed", "complete": False},
        headers=bearer(token),
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]

    fetched = client.get(f"/store/order/{order_id}", headers=bearer(token))
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == order_id
