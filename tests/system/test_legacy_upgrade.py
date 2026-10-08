import json
import os
import subprocess
import time
from datetime import datetime
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.system
LEGACY_IMAGE = (
    "andymentor/swagger-petstore@sha256:58733c8c19dac851fbc0b8033413e8e3966d74b921975bc73785bd455d0baae0"
)


def docker(*args: str, timeout: int = 180) -> str:
    """Выполняет ограниченную по времени команду для собственных Docker-ресурсов.

    :param timeout: Ограничение времени выполнения в секундах.
    :param args: Аргументы Docker для собственных тестовых ресурсов.
    :return: Результат описанной проверки или подготовки тестовых данных.
    """
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=timeout
    ).stdout.strip()


def start_image(image: str, container: str, volume: str, owner: str, network: str | None = None) -> str:
    """Запускает изолированный образ; новый API использует отдельную базу.

    :param image: Изображение либо его метаданные.
    :param container: Разрешённый контейнер изолированного тестового стенда.
    :param volume: Собственный том миграционного теста.
    :param owner: Идентификатор либо данные владельца ресурса.
    :param network: Сеть отдельной тестовой базы; None для старого общего образа.
    :return: Результат описанной проверки или подготовки тестовых данных.
    """
    args = [
        "run",
        "--detach",
        "--name",
        container,
        "--label",
        "petstore.upgrade-test=" + owner,
        "--publish",
        "127.0.0.1::8080",
    ]
    if network is None:
        args.extend(["--volume", volume + ":/var/lib/postgresql/data"])
    else:
        args.extend(["--network", network, "--env", "PETSTORE_DB_URL=postgresql://postgres:5432/petstore"])
    docker(*args, image)
    port = docker("port", container, "8080/tcp").rsplit(":", 1)[1]
    base = "http://127.0.0.1:" + port + "/api/v3"
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if httpx.get(base + "/health", timeout=2).status_code == 200:
                return base
        except httpx.HTTPError:
            pass
        time.sleep(1)
    pytest.fail("The isolated Java/Python upgrade container did not become ready")


def admin_headers(client: httpx.Client) -> dict[str, str]:
    """Авторизует администратора собственной миграционной базы.

    :param client: HTTP-клиент только текущего тестового стенда.
    :return: Результат описанной проверки или подготовки тестовых данных.
    """
    response = client.post("/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_existing_records_and_migration_checksums_survive_runtime_upgrade():
    candidate = os.getenv("PETSTORE_TEST_UPGRADE_IMAGE")
    if not candidate:
        pytest.skip("Set PETSTORE_TEST_UPGRADE_IMAGE for an isolated Java to Python upgrade")
    if candidate != "swagger-petstore-python:preview":
        pytest.fail("Upgrade tests must use only the isolated Python candidate")
    owner = uuid4().hex
    container = "petstore-python-upgrade-test-" + owner[:12]
    volume = "petstore-python-upgrade-data-" + owner[:12]
    network = "petstore-upgrade-network-" + owner[:12]
    database_container = "petstore-upgrade-db-" + owner[:12]
    docker("pull", LEGACY_IMAGE)
    docker("volume", "create", "--label", "petstore.upgrade-test=" + owner, volume)
    try:
        base = start_image(LEGACY_IMAGE, container, volume, owner)
        with httpx.Client(base_url=base, timeout=10) as client:
            registration = client.post(
                "/auth/register",
                json={
                    "username": "upgrade-" + owner[:20],
                    "email": owner + "@example.com",
                    "password": "UpgradePass123",
                    "firstName": "Upgrade",
                    "lastName": "Buyer",
                    "phone": "+79991234567",
                    "address": {"city": "Test", "street": "Test", "house": "1", "postalCode": "123456"},
                },
            )
            assert registration.status_code == 201
            user = registration.json()["user"]
            confirmation = urlsplit(registration.json()["confirmationUrl"])
            assert (
                client.get(confirmation.path.removeprefix("/api/v3") + "?" + confirmation.query).status_code
                == 200
            )
            admin = admin_headers(client)
            user_before = client.get("/users/" + user["id"], headers=admin).json()
            login = client.post("/auth/login", json={"email": user["email"], "password": "UpgradePass123"})
            assert login.status_code == 200
            user_auth = {"Authorization": "Bearer " + login.json()["access_token"]}
            pet_response = client.post(
                "/pet",
                headers=admin,
                json={"name": "Upgrade test pet", "price": 1299.99, "photoUrls": []},
            )
            assert pet_response.status_code == 201, pet_response.text
            pet = pet_response.json()
            order_response = client.post(
                "/store/order", headers=user_auth, json={"petId": pet["id"], "quantity": 1}
            )
            assert order_response.status_code == 201, order_response.text
            order = order_response.json()
            response = client.post(
                "/pet", headers=admin, json={"name": "Paid upgrade pet", "price": 12.75, "photoUrls": []}
            )
            assert response.status_code == 201
            paid_pet = response.json()
            response = client.post(
                "/store/order", headers=user_auth, json={"petId": paid_pet["id"], "quantity": 1}
            )
            assert response.status_code == 201
            paid_order = response.json()
            response = client.post("/store/order/" + paid_order["id"] + "/place", headers=user_auth)
            assert response.status_code == 200, response.text
            response = client.post(
                "/store/order/" + paid_order["id"] + "/payments",
                headers=user_auth | {"Idempotency-Key": str(uuid4())},
                json={
                    "cardNumber": "4242424242424242",
                    "expiryMonth": 12,
                    "expiryYear": 2099,
                    "cvv": "123",
                    "cardholderName": "Test Buyer",
                },
            )
            assert response.status_code == 201, response.text
            payment = response.json()
            paid_order = client.get("/store/order/" + paid_order["id"], headers=user_auth).json()
        history_query = "SELECT string_agg(version || ':' || checksum::text, ',' ORDER BY installed_rank) FROM flyway_schema_history WHERE success AND type = 'SQL'"
        history = docker("exec", container, "psql", "-U", "petstore", "-d", "petstore", "-tAc", history_query)
        docker("stop", "--timeout", "30", container)
        docker("rm", container)
        docker("network", "create", "--label", "petstore.upgrade-test=" + owner, network)
        docker(
            "run",
            "--detach",
            "--name",
            database_container,
            "--label",
            "petstore.upgrade-test=" + owner,
            "--network",
            network,
            "--network-alias",
            "postgres",
            "--env",
            "POSTGRES_USER=petstore",
            "--env",
            "POSTGRES_PASSWORD=petstore",
            "--env",
            "POSTGRES_DB=petstore",
            "--volume",
            volume + ":/var/lib/postgresql/data",
            "postgres:16.15-bookworm@sha256:bb3e1a57e5407e0a5280b4211980a5e537f4abd234a87014ac979849a78dd825",
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                docker("exec", database_container, "pg_isready", "-U", "petstore", "-d", "petstore")
                break
            except subprocess.CalledProcessError:
                time.sleep(1)
        else:
            pytest.fail("База не готова после перехода на отдельный контейнер")
        docker(
            "run",
            "--rm",
            "--network",
            network,
            "--env",
            "FLYWAY_URL=jdbc:postgresql://postgres:5432/petstore",
            "--env",
            "FLYWAY_USER=petstore",
            "--env",
            "FLYWAY_PASSWORD=petstore",
            "--entrypoint",
            "/opt/flyway/flyway",
            candidate,
            "-locations=filesystem:/app/resources/db/migration",
            "migrate",
        )
        base = start_image(candidate, container, volume, owner, network)
        with httpx.Client(base_url=base, timeout=10) as client:
            admin = admin_headers(client)
            user_after = client.get("/users/" + user["id"], headers=admin)
            assert user_after.status_code == 200
            assert user_after.json() == user_before
            pet_after = client.get("/pet/" + pet["id"])
            assert pet_after.status_code == 200
            assert pet_after.json() == pet
            order_after = client.get("/store/order/" + order["id"], headers=admin)
            assert order_after.status_code == 200
            actual = order_after.json()
            assert datetime.fromisoformat(actual.pop("createdAt")) == datetime.fromisoformat(
                order.pop("createdAt")
            )
            assert actual == order
            login_after = client.post(
                "/auth/login", json={"email": user["email"], "password": "UpgradePass123"}
            )
            assert login_after.status_code == 200
            paid_after = client.get("/store/order/" + paid_order["id"], headers=admin).json()
            for field in ("createdAt", "paymentExpiresAt"):
                assert datetime.fromisoformat(paid_after.pop(field)) == datetime.fromisoformat(
                    paid_order.pop(field)
                )
            assert paid_after == paid_order
            payment_after = client.get(
                "/store/order/" + paid_order["id"] + "/payments/" + payment["id"], headers=admin
            )
            assert payment_after.status_code == 200
            restored = payment_after.json()
            for field in ("createdAt", "updatedAt"):
                assert datetime.fromisoformat(restored.pop(field)) == datetime.fromisoformat(
                    payment.pop(field)
                )
            assert restored == payment
        migrated = docker(
            "exec", database_container, "psql", "-U", "petstore", "-d", "petstore", "-tAc", history_query
        )
        assert migrated.startswith(history + ",")
        assert len(migrated.split(",")) == 12
        assert len(history.split(",")) == 9
    finally:
        existing = docker("ps", "-aq", "--filter", "name=^/" + container + "$")
        if existing:
            labels = json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", container))
            assert labels["petstore.upgrade-test"] == owner
            docker("rm", "--force", "--volumes", container)
        if docker("ps", "-aq", "--filter", "name=^/" + database_container + "$"):
            labels = json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", database_container))
            assert labels["petstore.upgrade-test"] == owner
            docker("rm", "--force", database_container)
        if docker("network", "ls", "-q", "--filter", "name=^" + network + "$"):
            labels = json.loads(docker("network", "inspect", "--format", "{{json .Labels}}", network))
            assert labels["petstore.upgrade-test"] == owner
            docker("network", "rm", network)
        labels = json.loads(docker("volume", "inspect", "--format", "{{json .Labels}}", volume))
        assert labels["petstore.upgrade-test"] == owner
        docker("volume", "rm", volume)
