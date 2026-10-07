import hashlib
import io
import json
import os
import subprocess
import time
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from PIL import Image

pytestmark = pytest.mark.system


def docker(*arguments):
    """Run a bounded command only against the explicitly selected CI container."""
    return subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, check=True, timeout=60
    ).stdout.strip()


def wait_ready(client):
    """Wait for the isolated candidate without changing real application data."""
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if client.get("/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    pytest.fail("The commerce candidate did not become ready")


def verify_recreation(client, container, media, order, email, password, digest):
    """Replace only an isolated CI container while retaining its exact DB and media volumes."""
    original = json.loads(docker("inspect", container))[0]
    mounts = {mount["Destination"]: mount for mount in original["Mounts"]}
    destinations = ["/var/lib/postgresql/data", "/var/lib/petstore/media"]
    assert all(mounts[path]["Type"] == "volume" for path in destinations)
    replacement = "petstore-commerce-recreation-" + uuid4().hex[:12]
    owner = uuid4().hex
    args = [
        "run",
        "--detach",
        "--name",
        replacement,
        "--label",
        "petstore.commerce-test=" + owner,
        "--publish",
        "127.0.0.1::8080",
    ]
    for destination in destinations:
        args.extend(["--volume", mounts[destination]["Name"] + ":" + destination])
    args.append(original["Image"])
    docker("stop", "--time", "30", container)
    try:
        docker(*args)
        port = docker("port", replacement, "8080/tcp").rsplit(":", 1)[1]
        with httpx.Client(base_url="http://127.0.0.1:" + port + "/api/v3", timeout=20) as candidate:
            wait_ready(candidate)
            actual = candidate.get("/media/" + media["id"] + "/image")
            assert actual.status_code == 200 and hashlib.sha256(actual.content).digest() == digest
            buyer = login(candidate, email, password)
            restored = candidate.get("/store/orders/" + order["id"], headers=buyer)
            assert restored.status_code == 200 and restored.json()["paymentStatus"] == "PAID"
            payments = candidate.get("/store/orders/" + order["id"] + "/payments", headers=buyer).json()
            assert len(payments) == 1 and payments[0]["status"] == "SUCCEEDED"
    finally:
        if docker("ps", "-aq", "--filter", "name=^/" + replacement + "$"):
            labels = json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", replacement))
            assert labels["petstore.commerce-test"] == owner
            # Never remove volumes: both belong to the original isolated candidate.
            docker("rm", "--force", replacement)
        docker("start", container)
        wait_ready(client)


def login(client, email, password):
    """Authenticate a seeded admin or this fixture's own buyer."""
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.fixture
def shop():
    container = os.getenv("PETSTORE_COMMERCE_CONTAINER")
    base = os.getenv("BASE_URL")
    if not container or not base:
        pytest.skip("Set PETSTORE_COMMERCE_CONTAINER and BASE_URL for isolated shop acceptance")
    if container not in {"petstore-python-preview", "petstore-ci", "petstore-published-ci"}:
        pytest.fail("Commerce system tests may clean only their explicitly named CI containers")
    selected = urlsplit(base)
    port = int(docker("port", container, "8080/tcp").rsplit(":", 1)[1])
    if selected.hostname not in {"localhost", "127.0.0.1"} or selected.port != port:
        pytest.fail("BASE_URL must point to the explicitly selected local CI container")
    owned = {"users": [], "orders": [], "products": [], "pets": [], "categories": [], "media": []}
    with httpx.Client(base_url=base, timeout=20) as client:
        admin = login(client, "admin@example.com", "admin123")

        def created(response, kind):
            assert response.status_code == 201, response.text
            data = response.json()
            identifier = data["user"]["id"] if kind == "users" else data["id"]
            owned[kind].append(str(UUID(identifier)))
            return data

        try:
            suffix = uuid4().hex[:20]
            email, password = suffix + "@example.com", "CommercePass123"
            user = created(
                client.post(
                    "/auth/register",
                    json={
                        "username": "shop-" + suffix,
                        "email": email,
                        "password": password,
                        "firstName": "Test",
                        "lastName": "Buyer",
                        "phone": "+79991234567",
                        "address": {"city": "Test", "street": "Test", "house": "1", "postalCode": "123456"},
                    },
                ),
                "users",
            )
            link = urlsplit(user["confirmationUrl"])
            assert (
                client.get(link.path.removeprefix("/api/v3"), params=parse_qs(link.query)).status_code == 200
            )
            buyer = login(client, email, password)
            category = created(
                client.post(
                    "/admin/catalog/categories",
                    headers=admin,
                    json={"name": "System " + suffix, "kind": "product"},
                ),
                "categories",
            )
            picture = io.BytesIO()
            exif = Image.Exif()
            exif[315] = "Sensitive camera owner"
            Image.new("RGB", (640, 480), "blue").save(picture, format="JPEG", exif=exif.tobytes())
            media = created(
                client.post(
                    "/media",
                    headers=admin,
                    files={"file": ("not-stored-name.jpg", picture.getvalue(), "image/jpeg")},
                    data={"sourceType": "SUPPLIER", "sourceNote": "System test"},
                ),
                "media",
            )
            image = [{"mediaId": media["id"], "alt": "Test food", "isCover": True}]
            product = created(
                client.post(
                    "/products",
                    headers=admin,
                    json={
                        "sku": "SYSTEM-" + suffix,
                        "name": "System food",
                        "price": 125.25,
                        "stock": 3,
                        "categoryId": category["id"],
                        "productType": "FEED",
                        "brand": "System brand",
                        "animalTypes": ["cat"],
                        "feedForm": "DRY",
                        "lifeStages": ["ADULT"],
                        "netWeightGrams": 1000,
                        "ingredients": "Chicken",
                        "images": image,
                    },
                ),
                "products",
            )
            pet = created(
                client.post(
                    "/admin/pets",
                    headers=admin,
                    json={
                        "name": "System pet",
                        "price": 1000,
                        "animalType": "cat",
                        "categoryId": created(
                            client.post(
                                "/admin/catalog/categories",
                                headers=admin,
                                json={"name": "Pets-" + suffix, "kind": "pet"},
                            ),
                            "categories",
                        )["id"],
                        "images": image,
                    },
                ),
                "pets",
            )
            for path, record in (("/products/", product), ("/admin/pets/", pet)):
                response = client.post(
                    path + record["id"] + "/publish", headers=admin, json={"version": record["version"]}
                )
                assert response.status_code == 200, response.text
            current = client.get("/store/cart", headers=buyer).json()
            response = client.put(
                "/store/cart",
                headers=buyer | {"Idempotency-Key": str(uuid4())},
                json={
                    "version": current["version"],
                    "lines": [
                        {"kind": "product", "id": product["id"], "quantity": 2},
                        {"kind": "pet", "id": pet["id"], "quantity": 1},
                    ],
                },
            )
            assert response.status_code == 200, response.text
            order = created(
                client.post(
                    "/store/orders",
                    headers=buyer | {"Idempotency-Key": str(uuid4())},
                    json={"cartVersion": response.json()["version"]},
                ),
                "orders",
            )
            response = client.post(
                "/store/orders/" + order["id"] + "/place",
                headers=buyer | {"Idempotency-Key": str(uuid4())},
                json={"version": order["version"]},
            )
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 1250.5 and len(response.json()["lines"]) == 2
            key = str(uuid4())
            payment = {
                "cardNumber": "4242424242424242",
                "expiryMonth": 12,
                "expiryYear": 2099,
                "cvv": "123",
                "cardholderName": "Test Buyer",
            }
            response = client.post(
                "/store/orders/" + order["id"] + "/payments",
                headers=buyer | {"Idempotency-Key": key},
                json=payment,
            )
            assert response.status_code == 201 and response.json()["amount"] == 1250.5, response.text
            replay = client.post(
                "/store/orders/" + order["id"] + "/payments",
                headers=buyer | {"Idempotency-Key": key},
                json=payment,
            )
            assert replay.status_code == 200 and replay.json()["id"] == response.json()["id"]
            yield client, container, product, media, order, email, password
        finally:
            # Never delete by username/email: UUIDs below were recorded only after successful creation.
            admin = login(client, "admin@example.com", "admin123")
            for identifier in owned["orders"]:
                current = client.get("/store/orders/" + identifier, headers=admin)
                if current.status_code == 200 and current.json()["status"] in {"placed", "approved"}:
                    cancelled = client.post(
                        "/store/orders/" + identifier + "/cancel",
                        headers=admin,
                        json={"version": current.json()["version"]},
                    )
                    assert cancelled.status_code == 200, cancelled.text
                assert client.delete("/store/orders/" + identifier, headers=admin).status_code == 204
            for identifier in owned["pets"]:
                assert client.delete("/pet/" + identifier, headers=admin).status_code == 204
            for identifier in owned["products"]:
                docker(
                    "exec",
                    container,
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "petstore",
                    "-d",
                    "petstore",
                    "-c",
                    f"BEGIN; DELETE FROM catalog_images WHERE product_id='{identifier}'::uuid; DELETE FROM stock_adjustments WHERE product_id='{identifier}'::uuid; DELETE FROM products WHERE id='{identifier}'::uuid; COMMIT;",
                )
            for identifier in owned["media"]:
                assert client.delete("/media/" + identifier, headers=admin).status_code == 204
            for identifier in owned["categories"]:
                docker(
                    "exec",
                    container,
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "petstore",
                    "-d",
                    "petstore",
                    "-c",
                    f"DELETE FROM catalog_categories WHERE id='{identifier}'::uuid",
                )
            for identifier in owned["users"]:
                assert client.delete("/users/" + identifier, headers=admin).status_code == 204


def test_full_shop_acceptance_and_sanitized_photo_survive_recreation(shop):
    client, container, product, media, order, email, password = shop
    image = client.get("/media/" + media["id"] + "/image")
    assert image.status_code == 200 and b"Sensitive camera owner" not in image.content
    with Image.open(io.BytesIO(image.content)) as result:
        assert not result.getexif() and result.size == (640, 480)
    thumb = client.get("/media/" + media["id"] + "/thumb")
    with Image.open(io.BytesIO(thumb.content)) as result:
        assert max(result.size) <= 400
    digest = hashlib.sha256(image.content).digest()
    verify_recreation(client, container, media, order, email, password, digest)
    assert hashlib.sha256(client.get("/media/" + media["id"] + "/image").content).digest() == digest
    buyer = login(client, email, password)
    current = client.get("/store/orders/" + order["id"], headers=buyer)
    assert current.status_code == 200 and current.json()["paymentStatus"] == "PAID"
    history = client.get("/store/orders/" + order["id"] + "/payments", headers=buyer).json()
    assert len(history) == 1 and history[0]["status"] == "SUCCEEDED"
    assert client.get("/products/" + product["id"]).json()["availableQuantity"] == 1
