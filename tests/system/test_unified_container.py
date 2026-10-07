"""Verify the complete application and persistence within one isolated container."""

import hashlib
import io
import os
import subprocess
import time
from uuid import uuid4

import httpx
import pytest
from PIL import Image

pytestmark = pytest.mark.system


def test_single_container_store_mail_and_restart():
    """Retain an API draft, photograph and actual email after restarting the same container."""
    container = os.getenv("PETSTORE_UNIFIED_CONTAINER")
    if not container:
        pytest.skip("Set PETSTORE_UNIFIED_CONTAINER for the isolated combined image")
    api = os.getenv("BASE_URL", "http://127.0.0.1:18081/api/v3")
    store = os.getenv("PETSTORE_STORE_UI_URL", "http://127.0.0.1:8089")
    mail = os.getenv("PETSTORE_MAIL_UI_URL", "http://127.0.0.1:18025")
    marker = "unified-" + uuid4().hex[:20]
    product_id = user_id = message_id = None
    with httpx.Client(base_url=api, timeout=20) as client:
        login = client.post("/auth/login", json={"email": "admin@example.com", "password": "admin123"})
        assert login.status_code == 200
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        try:
            for path in ("/", "/catalog", "/register"):
                response = httpx.get(store + path, timeout=10)
                assert response.status_code == 200 and 'id="root"' in response.text
            processes = subprocess.run(
                ["docker", "top", container, "-eo", "pid,args"],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout
            for process in ("uvicorn", "postgres", "nginx", "Rnwood.Smtp4dev.dll"):
                assert process in processes
            picture = io.BytesIO()
            Image.new("RGB", (300, 180), "#e8d9c2").save(picture, format="PNG")
            uploaded = client.post(
                "/media",
                headers=headers,
                files={"file": ("review.png", picture.getvalue(), "image/png")},
                data={"sourceType": "DEMO"},
            )
            assert uploaded.status_code == 201
            media_id = uploaded.json()["id"]
            created = client.post(
                "/products", headers=headers, json={"name": marker, "images": [{"mediaId": media_id}]}
            )
            assert created.status_code == 201
            product_id = created.json()["id"]
            image = client.get(f"/media/{media_id}/image", headers=headers)
            checksum = hashlib.sha256(image.content).hexdigest()
            registered = client.post(
                "/auth/register",
                json={"username": marker, "email": marker + "@petstore.test", "password": "UnifiedPass123"},
            )
            assert registered.status_code == 201
            user_id = registered.json()["user"]["id"]
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                messages = httpx.get(
                    mail + "/api/Messages",
                    params={"mailboxName": "Tests", "searchTerms": marker, "pageSize": 100},
                ).json()["results"]
                if messages:
                    message_id = messages[0]["id"]
                    break
                time.sleep(0.2)
            assert message_id is not None
            subprocess.run(["docker", "restart", container], check=True, capture_output=True, timeout=60)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    if (
                        client.get("/health").status_code == 200
                        and httpx.get(mail + "/api/Mailboxes").status_code == 200
                    ):
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            login = client.post("/auth/login", json={"email": "admin@example.com", "password": "admin123"})
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            assert client.get(f"/admin/products/{product_id}", headers=headers).json()["name"] == marker
            assert (
                hashlib.sha256(client.get(f"/media/{media_id}/image", headers=headers).content).hexdigest()
                == checksum
            )
            assert httpx.get(mail + f"/api/Messages/{message_id}/plaintext").status_code == 200
            assert client.get(f"/users/{user_id}", headers=headers).status_code == 200
        finally:
            if user_id:
                client.delete(f"/users/{user_id}", headers=headers)
            if product_id:
                current = client.get(f"/admin/products/{product_id}", headers=headers)
                if current.status_code == 200:
                    client.post(
                        f"/products/{product_id}/archive",
                        headers=headers,
                        json={"version": current.json()["version"]},
                    )
            if message_id:
                httpx.delete(mail + f"/api/Messages/{message_id}")
