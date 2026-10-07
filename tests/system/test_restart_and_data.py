import os
import subprocess
import time
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.system


def run_docker(*args: str) -> str:
    """Run a bounded command against the explicitly selected isolated test container.

    :param args: Docker arguments without credentials or request payloads.
    """
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=60
    ).stdout.strip()


@pytest.fixture
def restart_record():
    url = os.getenv("PETSTORE_UI_URL")
    container = os.getenv("PETSTORE_RESTART_CONTAINER")
    if not url or not container:
        pytest.skip("Set PETSTORE_UI_URL and PETSTORE_RESTART_CONTAINER for the isolated restart test")
    if container != "petstore-python-preview":
        pytest.fail("Restart tests may touch only petstore-python-preview, never a released container")
    with httpx.Client(base_url=url.rstrip("/") + "/api/v3", timeout=10) as client:
        response = client.post(
            "/auth/register",
            json={
                "username": "restart-" + uuid4().hex[:20],
                "email": uuid4().hex + "@example.com",
                "password": "RestartPass123",
            },
        )
        assert response.status_code == 201, response.text
        user = response.json()["user"]
        try:
            yield client, container, user
        finally:
            login = client.post("/auth/login", json={"email": "admin@example.com", "password": "admin123"})
            assert login.status_code == 200
            deleted = client.delete(
                f"/users/{user['id']}", headers={"Authorization": "Bearer " + login.json()["access_token"]}
            )
            assert deleted.status_code == 204


def test_existing_user_and_flyway_history_survive_restart(restart_record):
    client, container, before = restart_record
    query = "SELECT string_agg(version || ':' || checksum::text, ',' ORDER BY installed_rank) FROM flyway_schema_history WHERE success AND type = 'SQL'"
    history_before = run_docker("exec", container, "psql", "-U", "petstore", "-d", "petstore", "-tAc", query)
    run_docker("restart", container)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if client.get("/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    else:
        pytest.fail("The isolated candidate did not recover after restart")
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert login.status_code == 200
    response = client.get(
        f"/users/{before['id']}", headers={"Authorization": "Bearer " + login.json()["access_token"]}
    )
    assert response.status_code == 200
    assert response.json() == before
    history_after = run_docker("exec", container, "psql", "-U", "petstore", "-d", "petstore", "-tAc", query)
    assert history_after == history_before
    assert len(history_after.split(",")) == 12
