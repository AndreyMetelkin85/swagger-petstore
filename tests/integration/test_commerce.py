import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from PIL import Image

from petstore.config import Settings
from petstore.service.media_service import MediaService

pytestmark = pytest.mark.integration


def jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (16, 12), "blue").save(buffer, format="JPEG")
    return buffer.getvalue()


@dataclass
class Commerce:
    scenario: object
    categories: list = field(default_factory=list)
    products: list = field(default_factory=list)
    pets: list = field(default_factory=list)
    orders: list = field(default_factory=list)
    media: list = field(default_factory=list)

    @property
    def client(self):
        return self.scenario.client

    @property
    def admin(self):
        return self.scenario.admin

    def category(self, kind="product"):
        response = self.client.post(
            "/admin/catalog/categories", headers=self.admin, json={"name": uuid4().hex, "kind": kind}
        )
        assert response.status_code == 201, response.text
        result = response.json()
        self.categories.append(result["id"])
        return result

    def image(self):
        response = self.client.post(
            "/media",
            headers=self.admin,
            files={"file": ("ignored.jpg", jpeg(), "text/plain")},
            data={"sourceType": "OWN", "sourceNote": "Test"},
        )
        assert response.status_code == 201, response.text
        result = response.json()
        self.media.append(result["id"])
        return result

    def product(self, stock=5, price=100):
        category, image = self.category(), self.image()
        request = {
            "sku": uuid4().hex,
            "name": "Test food",
            "price": price,
            "categoryId": category["id"],
            "stock": stock,
            "productType": "FEED",
            "feedForm": "DRY",
            "netWeightGrams": 1000,
            "ingredients": "Chicken",
            "animalTypes": ["cat"],
            "images": [{"mediaId": image["id"], "alt": "Food"}],
        }
        response = self.client.post("/products", headers=self.admin, json=request)
        assert response.status_code == 201, response.text
        result = response.json()
        self.products.append(result["id"])
        published = self.client.post(
            f"/products/{result['id']}/publish", headers=self.admin, json={"version": result["version"]}
        )
        assert published.status_code == 200, published.text
        return published.json(), request

    def pet(self, price=50):
        image = self.image()
        response = self.client.post(
            "/admin/pets",
            headers=self.admin,
            json={
                "name": "Test cat",
                "price": price,
                "animalType": "cat",
                "images": [{"mediaId": image["id"]}],
            },
        )
        assert response.status_code == 201, response.text
        result = response.json()
        self.pets.append(result["id"])
        published = self.client.post(
            f"/admin/pets/{result['id']}/publish", headers=self.admin, json={"version": result["version"]}
        )
        assert published.status_code == 200, published.text
        return published.json()

    def cart(self, headers, lines, key=None):
        current = self.client.get("/store/cart", headers=headers)
        assert current.status_code == 200, current.text
        response = self.client.put(
            "/store/cart",
            headers=headers | ({"Idempotency-Key": str(key)} if key else {}),
            json={"version": current.json()["version"], "lines": lines},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def draft(self, headers, cart):
        response = self.client.post(
            "/store/orders",
            headers=headers | {"Idempotency-Key": str(uuid4())},
            json={"cartVersion": cart["version"]},
        )
        assert response.status_code == 201, response.text
        result = response.json()
        self.orders.append(result["id"])
        return result

    def place(self, headers, order, token=None):
        return self.client.post(
            f"/store/orders/{order['id']}/place",
            headers=headers | {"Idempotency-Key": str(token or uuid4())},
            json={"version": order["version"]},
        )

    def pay(self, headers, order, key=None, card="4242424242424242"):
        return self.client.post(
            f"/store/orders/{order['id']}/payments",
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
def commerce(scenario):
    result = Commerce(scenario)
    try:
        yield result
    finally:
        with scenario.database.connect() as connection:
            for identifier in result.orders:
                connection.execute("DELETE FROM payments WHERE order_id=%s", (identifier,))
                connection.execute("DELETE FROM order_lines WHERE order_id=%s", (identifier,))
                connection.execute("DELETE FROM store_orders WHERE id=%s", (identifier,))
            for identifier in result.products:
                connection.execute("DELETE FROM catalog_images WHERE product_id=%s", (identifier,))
                connection.execute("DELETE FROM stock_adjustments WHERE product_id=%s", (identifier,))
                connection.execute("DELETE FROM products WHERE id=%s", (identifier,))
            for identifier in result.pets:
                connection.execute("DELETE FROM catalog_images WHERE pet_id=%s", (identifier,))
                connection.execute("DELETE FROM pets WHERE id=%s", (identifier,))
            for identifier in result.media:
                row = connection.execute(
                    "DELETE FROM media WHERE id=%s RETURNING *", (identifier,)
                ).fetchone()
                if row:
                    service = MediaService(scenario.database, Settings())
                    for thumbnail in (True, False):
                        service.path(UUID(identifier), row["mime_type"], thumbnail).unlink(missing_ok=True)
            for identifier in result.categories:
                connection.execute("DELETE FROM catalog_categories WHERE id=%s", (identifier,))


def test_full_acceptance_food_photo_pet_one_payment_refund_and_single_release(commerce):
    _, _, user = commerce.scenario.user()
    product, _ = commerce.product(stock=3, price=125.25)
    pet = commerce.pet(price=1000)
    cart = commerce.cart(
        user,
        [
            {"kind": "product", "id": product["id"], "quantity": 2},
            {"kind": "pet", "id": pet["id"], "quantity": 1},
        ],
    )
    draft = commerce.draft(user, cart)
    assert draft["paymentStatus"] == "NOT_STARTED" and draft["total"] is None
    assert commerce.client.get("/products/" + product["id"]).json()["reserved"] == 0
    placed = commerce.place(user, draft)
    assert placed.status_code == 200, placed.text
    assert placed.json()["total"] == 1250.50
    payment_key = uuid4()
    paid = commerce.pay(user, draft, payment_key)
    assert paid.status_code == 201, paid.text
    replay = commerce.pay(user, draft, payment_key)
    assert replay.status_code == 200 and replay.json()["id"] == paid.json()["id"]
    current = commerce.client.get("/store/orders/" + draft["id"], headers=user).json()
    cancelled = commerce.client.post(
        f"/store/orders/{draft['id']}/cancel", headers=user, json={"version": current["version"]}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["paymentStatus"] == "REFUNDED"
    repeated = commerce.client.post(
        f"/store/orders/{draft['id']}/cancel", headers=user, json={"version": cancelled.json()["version"]}
    )
    assert repeated.status_code == 409
    assert commerce.client.get("/products/" + product["id"]).json()["availableQuantity"] == 3
    assert commerce.client.get("/catalog/pets/" + pet["id"]).json()["status"] == "available"
    assert (
        commerce.client.get(f"/store/orders/{draft['id']}/payments", headers=user).json()[0]["status"]
        == "REFUNDED"
    )


def test_publishing_filters_versions_sku_category_and_media_references(commerce):
    product, request = commerce.product()
    duplicate = commerce.client.post("/products", headers=commerce.admin, json=request)
    assert duplicate.status_code == 409 and duplicate.json()["error"] == "SKU_ALREADY_EXISTS"
    stale = commerce.client.put(
        "/products/" + product["id"], headers=commerce.admin, json=request | {"version": 0}
    )
    assert stale.status_code == 409
    result = commerce.client.get(
        "/products", params={"q": "Test", "animalType": "cat", "sort": "priceDesc", "pageSize": 1}
    )
    assert result.status_code == 200 and result.json()["total"] >= 1
    assert commerce.client.get("/media/" + commerce.media[-1] + "/image").status_code == 200
    used = commerce.client.delete("/media/" + commerce.media[-1], headers=commerce.admin)
    assert used.status_code == 409 and used.json()["error"] == "MEDIA_IN_USE"
    category = commerce.client.get("/admin/catalog/categories", headers=commerce.admin).json()
    category = next(r for r in category if r["id"] == product["categoryId"])
    updated = commerce.client.put(
        "/admin/catalog/categories/" + category["id"],
        headers=commerce.admin,
        json=category | {"active": False, "archived": False},
    )
    # DTO output-only fields are not an update command.
    assert updated.status_code == 422
    updated = commerce.client.put(
        "/admin/catalog/categories/" + category["id"],
        headers=commerce.admin,
        json={key: category[key] for key in ("name", "kind", "version")} | {"active": False},
    )
    assert updated.status_code == 200
    assert commerce.client.get("/products/" + product["id"]).status_code == 200
    assert category["id"] not in {r["id"] for r in commerce.client.get("/catalog/categories").json()}


def test_cart_version_and_replayed_guest_merge(commerce):
    _, _, user = commerce.scenario.user()
    product, _ = commerce.product()
    current = commerce.client.get("/store/cart", headers=user).json()
    payload = {
        "version": current["version"],
        "lines": [{"kind": "product", "id": product["id"], "quantity": 2}],
    }
    key = uuid4()
    headers = user | {"Idempotency-Key": str(key)}
    first = commerce.client.put("/store/cart", headers=headers, json=payload)
    second = commerce.client.put("/store/cart", headers=headers, json=payload)
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    assert second.json()["lines"][0]["quantity"] == 2
    changed = commerce.client.put("/store/cart", headers=headers, json=payload | {"lines": []})
    assert changed.status_code == 409 and changed.json()["error"] == "IDEMPOTENCY_KEY_REUSED"
    stale = commerce.client.put("/store/cart", headers=user, json=payload)
    assert stale.status_code == 409 and stale.json()["error"] == "CART_VERSION_CONFLICT"


def test_price_change_and_all_or_nothing_reservation(commerce):
    _, _, user = commerce.scenario.user()
    product, request = commerce.product(stock=1)
    pet = commerce.pet()
    cart = commerce.cart(
        user,
        [
            {"kind": "pet", "id": pet["id"], "quantity": 1},
            {"kind": "product", "id": product["id"], "quantity": 2},
        ],
    )
    draft = commerce.draft(user, cart)
    failure = commerce.place(user, draft)
    assert failure.status_code == 409 and failure.json()["error"] == "INSUFFICIENT_STOCK"
    assert commerce.client.get("/catalog/pets/" + pet["id"]).json()["status"] == "available"
    assert commerce.client.get("/products/" + product["id"]).json()["reserved"] == 0
    cart = commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 1}])
    draft = commerce.draft(user, cart)
    update = commerce.client.put(
        "/products/" + product["id"],
        headers=commerce.admin,
        json=request | {"price": 101, "version": product["version"]},
    )
    assert update.status_code == 200, update.text
    failure = commerce.place(user, draft)
    assert failure.status_code == 409 and failure.json()["error"] == "PRICE_CHANGED"


def test_last_stock_parallel_place_has_one_winner(commerce):
    _, _, first = commerce.scenario.user()
    _, _, second = commerce.scenario.user()
    product, _ = commerce.product(stock=1)
    line = [{"kind": "product", "id": product["id"], "quantity": 1}]
    a = commerce.draft(first, commerce.cart(first, line))
    b = commerce.draft(second, commerce.cart(second, line))
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda pair: commerce.place(*pair), [(first, a), (second, b)]))
    assert sorted(r.status_code for r in outcomes) == [200, 409]
    assert commerce.client.get("/products/" + product["id"]).json()["reserved"] == 1


def test_legacy_and_mixed_share_pet_reservation_lock(commerce):
    _, _, first = commerce.scenario.user()
    _, _, second = commerce.scenario.user()
    pet = commerce.pet()
    draft = commerce.draft(first, commerce.cart(first, [{"kind": "pet", "id": pet["id"], "quantity": 1}]))
    old = commerce.client.post("/store/order", headers=second, json={"petId": pet["id"], "quantity": 1})
    assert old.status_code == 201
    commerce.orders.append(old.json()["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda fn: fn(),
                [
                    lambda: commerce.place(first, draft),
                    lambda: commerce.client.post(
                        "/store/order/" + old.json()["id"] + "/place", headers=second
                    ),
                ],
            )
        )
    assert sorted(r.status_code for r in outcomes) == [200, 409]


def test_expiry_payment_and_stock_adjustment_safety(commerce):
    _, _, user = commerce.scenario.user()
    product, _ = commerce.product(stock=2)
    draft = commerce.draft(
        user, commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 2}])
    )
    placed = commerce.place(user, draft)
    assert placed.status_code == 200
    current = commerce.client.get("/admin/products/" + product["id"], headers=commerce.admin).json()
    decrease = commerce.client.post(
        "/products/" + product["id"] + "/stock-adjustments",
        headers=commerce.admin,
        json={"version": current["version"], "delta": -1, "reason": "Test"},
    )
    assert decrease.status_code == 409
    with commerce.scenario.database.connect() as connection:
        connection.execute(
            "UPDATE store_orders SET payment_expires_at=CURRENT_TIMESTAMP-INTERVAL '1 minute' WHERE id=%s",
            (draft["id"],),
        )
    paid = commerce.pay(user, draft)
    assert paid.status_code == 410, paid.text
    assert commerce.client.get("/products/" + product["id"]).json()["reserved"] == 0
    assert commerce.client.get("/store/orders/" + draft["id"], headers=user).json()["status"] == "expired"


def test_unavailable_cart_lines_and_role_guards(commerce):
    _, _, user = commerce.scenario.user()
    cart = commerce.cart(user, [{"kind": "product", "id": str(uuid4()), "quantity": 1}])
    assert cart["lines"][0]["available"] is False and cart["lines"][0]["reason"] == "PRODUCT_NOT_FOUND"
    assert commerce.client.get("/admin/products", headers=user).status_code == 403
    assert commerce.client.post("/media", headers=user, files={"file": ("x.jpg", jpeg())}).status_code == 403
    assert commerce.client.get("/store/cart").status_code == 401
    assert (
        commerce.client.post(
            "/telemetry/client-events",
            json={"events": [{"event": "api_result", "httpStatus": 200, "durationMs": 1}]},
        ).status_code
        == 204
    )
    assert (
        commerce.client.post(
            "/telemetry/client-events", json={"events": [{"event": "api_result", "password": "NeverLog"}]}
        ).status_code
        == 422
    )
