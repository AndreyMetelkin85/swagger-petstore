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
    """Run a bounded Docker command for this test's uniquely named resources.

    :param args: Arguments without passwords or user request bodies.
    :param timeout: Maximum execution time in seconds.
    """
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=timeout
    ).stdout.strip()


def start_image(image: str, container: str, volume: str, owner: str) -> str:
    """Start a migration test image and wait for both API and PostgreSQL.

    :param image: Explicit legacy digest or the isolated candidate image.
    :param container: Unique test container name.
    :param volume: Unique test volume shared by the two runtimes.
    :param owner: Resource ownership label checked during cleanup.
    """
    docker(
        "run",
        "--detach",
        "--name",
        container,
        "--label",
        "petstore.upgrade-test=" + owner,
        "--publish",
        "127.0.0.1::8080",
        "--volume",
        volume + ":/var/lib/postgresql/data",
        image,
    )
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
    """Authenticate the seeded administrator of the isolated test database.

    :param client: HTTP client connected only to the migration test container.
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
        history_query = "SELECT string_agg(version || ':' || checksum::text, ',' ORDER BY installed_rank) FROM flyway_schema_history WHERE success AND type = 'SQL'"
        history = docker("exec", container, "psql", "-U", "petstore", "-d", "petstore", "-tAc", history_query)
        docker("stop", "--time", "30", container)
        docker("rm", container)
        base = start_image(candidate, container, volume, owner)
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
        migrated = docker(
            "exec", container, "psql", "-U", "petstore", "-d", "petstore", "-tAc", history_query
        )
        assert migrated.startswith(history + ",")
        assert len(migrated.split(",")) == 11
        assert len(history.split(",")) == 9
    finally:
        existing = docker("ps", "-aq", "--filter", "name=^/" + container + "$")
        if existing:
            labels = json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", container))
            assert labels["petstore.upgrade-test"] == owner
            docker("rm", "--force", container)
        labels = json.loads(docker("volume", "inspect", "--format", "{{json .Labels}}", volume))
        assert labels["petstore.upgrade-test"] == owner
        docker("volume", "rm", volume)
