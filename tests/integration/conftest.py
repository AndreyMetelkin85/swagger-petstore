import os
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from petstore.app import create_app
from petstore.config import Settings
from petstore.data.database import Database

ADDRESS = {"city": "Москва", "street": "Тестовая", "house": "1", "apartment": None, "postalCode": "123456"}


@pytest.fixture
def integration_database():
    url = os.getenv("PETSTORE_TEST_DB_URL")
    if not url:
        pytest.skip("Set PETSTORE_TEST_DB_URL for a dedicated migrated test database")
    if urlsplit(url).path != "/petstore_python_test":
        pytest.fail("Integration tests require the dedicated petstore_python_test database")
    settings = Settings(db_url=url, expire_interval=0, public_base_url="http://testserver/api/v3")
    database = Database(settings)
    yield settings, database


@dataclass
class Scenario:
    client: TestClient
    database: Database
    admin: dict[str, str]
    users: list[UUID] = field(default_factory=list)
    pets: list[UUID] = field(default_factory=list)
    orders: list[UUID] = field(default_factory=list)

    def user(self, active=True, profile=True):
        request = {
            "username": "py-" + uuid4().hex[:20],
            "email": uuid4().hex + "@example.com",
            "password": "ValidPass123",
        }
        if profile:
            request |= {
                "firstName": "Тест",
                "lastName": "Пользователь",
                "phone": "+79991234567",
                "address": ADDRESS,
            }
        response = self.client.post("/auth/register", json=request)
        assert response.status_code == 201, response.text
        data = response.json()
        self.users.append(UUID(data["user"]["id"]))
        if active:
            response = self.client.get(
                urlsplit(data["confirmationUrl"]).path.removeprefix("/api/v3"),
                params={"code": parse_qs(urlsplit(data["confirmationUrl"]).query)["code"][0]},
            )
            assert response.status_code == 200, response.text
            response = self.client.post(
                "/auth/login", json={"email": request["email"], "password": request["password"]}
            )
            assert response.status_code == 200, response.text
            headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        else:
            headers = {}
        return request, data, headers

    def pet(self, price="10.25"):
        response = self.client.post(
            "/pet",
            headers=self.admin,
            json={
                "name": "Python test pet",
                "price": price,
                "category": {"name": "Tests"},
                "tags": [{"name": "python"}],
                "photoUrls": [],
            },
        )
        assert response.status_code == 201, response.text
        data = response.json()
        self.pets.append(UUID(data["id"]))
        return data

    def draft(self, pet, headers):
        response = self.client.post("/store/order", headers=headers, json={"petId": pet["id"], "quantity": 1})
        assert response.status_code == 201, response.text
        data = response.json()
        self.orders.append(UUID(data["id"]))
        return data

    def place(self, order, headers):
        response = self.client.post(f"/store/order/{order['id']}/place", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    def pay(self, order, headers, card="4242424242424242", key=None):
        return self.client.post(
            f"/store/order/{order['id']}/payments",
            headers=headers | {"Idempotency-Key": str(key or uuid4())},
            json={
                "cardNumber": card,
                "expiryMonth": 12,
                "expiryYear": 2099,
                "cvv": "123",
                "cardholderName": "Test User",
            },
        )


@pytest.fixture
def scenario(integration_database):
    settings, database = integration_database
    app = create_app(settings=settings, database=database)
    with TestClient(app, base_url="http://testserver/api/v3") as client:
        response = client.post("/auth/login", json={"email": "admin@example.com", "password": "admin123"})
        assert response.status_code == 200, response.text
        scenario = Scenario(client, database, {"Authorization": "Bearer " + response.json()["access_token"]})
        try:
            yield scenario
        finally:
            # Exact UUIDs created by this fixture only; no email/username guesses or broad deletes.
            with database.connect() as connection:
                for order_id in scenario.orders:
                    connection.execute("DELETE FROM payments WHERE order_id = %s", (order_id,))
                    connection.execute("DELETE FROM store_orders WHERE id = %s", (order_id,))
                for user_id in scenario.users:
                    connection.execute("DELETE FROM api_idempotency WHERE user_id=%s", (user_id,))
                    connection.execute("DELETE FROM cart_lines WHERE user_id=%s", (user_id,))
                    connection.execute("DELETE FROM carts WHERE user_id=%s", (user_id,))
                    connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
                for pet_id in scenario.pets:
                    connection.execute("DELETE FROM pets WHERE id = %s", (pet_id,))
