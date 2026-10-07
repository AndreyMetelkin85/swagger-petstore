from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from tests.integration.test_commerce import commerce as commerce

from petstore.config import Settings
from petstore.data.cart_data import CartData
from petstore.model.commerce import ProductCommand
from petstore.service.catalog_service import CatalogService
from petstore.service.media_service import MediaService

pytestmark = pytest.mark.integration


def test_changed_cart_rejects_place_without_any_reserve(commerce):
    _, _, user = commerce.scenario.user()
    product, _ = commerce.product()
    cart = commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 1}])
    draft = commerce.draft(user, cart)
    newer = commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 2}])
    response = commerce.place(user, draft)
    assert response.status_code == 409 and response.json()["error"] == "CART_VERSION_CONFLICT"
    assert commerce.client.get("/store/cart", headers=user).json() == newer
    assert commerce.client.get("/store/orders/" + draft["id"], headers=user).json()["status"] == "draft"
    assert commerce.client.get("/products/" + product["id"]).json()["reserved"] == 0


def test_place_clears_cart_once_and_replay_keeps_new_positions(commerce):
    _, _, user = commerce.scenario.user()
    product, _ = commerce.product()
    cart = commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 1}])
    draft = commerce.draft(user, cart)
    key = uuid4()
    first = commerce.place(user, draft, key)
    assert first.status_code == 200
    empty = commerce.client.get("/store/cart", headers=user).json()
    assert empty["lines"] == [] and empty["version"] == cart["version"] + 1
    newer = commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 2}])
    repeat = commerce.place(user, draft, key)
    assert repeat.json() == first.json()
    assert commerce.client.get("/store/cart", headers=user).json() == newer
    assert commerce.client.get("/products/" + product["id"]).json()["reserved"] == 1


def test_failure_during_cart_clear_rolls_back_order_and_reserve(commerce, monkeypatch):
    _, _, user = commerce.scenario.user()
    product, _ = commerce.product()
    cart = commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 1}])
    draft = commerce.draft(user, cart)

    def fail(*args):
        raise RuntimeError("simulated cart write failure")

    with monkeypatch.context() as patch:
        patch.setattr(CartData, "bump_version", fail)
        assert commerce.place(user, draft).status_code == 500
    assert commerce.client.get("/store/cart", headers=user).json() == cart
    assert commerce.client.get("/products/" + product["id"]).json()["reserved"] == 0
    assert commerce.client.get("/store/orders/" + draft["id"], headers=user).json()["status"] == "draft"


def test_two_drafts_from_same_cart_have_only_one_successful_place(commerce):
    _, _, user = commerce.scenario.user()
    product, _ = commerce.product(stock=5)
    cart = commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 1}])
    drafts = [commerce.draft(user, cart), commerce.draft(user, cart)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda draft: commerce.place(user, draft), drafts))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert next(r for r in results if r.status_code == 409).json()["error"] == "CART_VERSION_CONFLICT"
    assert commerce.client.get("/products/" + product["id"]).json()["reserved"] == 1


@pytest.mark.parametrize("kind", ["product", "pet"])
def test_name_only_draft_is_saved_and_published_only_after_completion(commerce, kind):
    path = "/products" if kind == "product" else "/admin/pets"
    created = commerce.client.post(path, headers=commerce.admin, json={"name": "Partial draft"})
    assert created.status_code == 201, created.text
    draft = created.json()
    (commerce.products if kind == "product" else commerce.pets).append(draft["id"])
    admin_path = "/admin/products" if kind == "product" else path
    assert commerce.client.get(admin_path + "/" + draft["id"], headers=commerce.admin).json() == draft
    assert draft["price"] is None
    if kind == "product":
        assert draft["sku"] is None and draft["productType"] is None
    failed = commerce.client.post(
        path + "/" + draft["id"] + "/publish", headers=commerce.admin, json={"version": draft["version"]}
    )
    assert failed.status_code == 422 and failed.json()["error"] == "PUBLICATION_INCOMPLETE"
    assert {"categoryId", "price", "images"} <= {e["field"] for e in failed.json()["details"]}
    category, photo = commerce.category(kind), commerce.image()
    payload = {
        "name": "Complete",
        "price": 10,
        "categoryId": category["id"],
        "images": [{"mediaId": photo["id"]}],
        "version": draft["version"],
    }
    payload |= (
        {"sku": uuid4().hex, "productType": "OTHER", "animalTypes": ["cat"]}
        if kind == "product"
        else {"animalType": "cat"}
    )
    updated = commerce.client.put(path + "/" + draft["id"], headers=commerce.admin, json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["images"][0]["alt"] == "Complete, фото 1"
    published = commerce.client.post(
        path + "/" + draft["id"] + "/publish",
        headers=commerce.admin,
        json={"version": updated.json()["version"]},
    )
    assert published.status_code == 200, published.text
    invalid = commerce.client.put(
        path + "/" + draft["id"],
        headers=commerce.admin,
        json={"name": "Incomplete", "version": published.json()["version"]},
    )
    assert invalid.status_code == 422
    assert (
        commerce.client.get(admin_path + "/" + draft["id"], headers=commerce.admin).json() == published.json()
    )


def test_payment_debits_goods_refund_restores_once_and_delivery_does_not_debit_twice(commerce):
    _, _, user = commerce.scenario.user()
    product, _ = commerce.product(stock=5)
    draft = commerce.draft(
        user, commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 2}])
    )
    placed = commerce.place(user, draft).json()
    key = uuid4()
    assert commerce.pay(user, placed, key=key).status_code == 201
    after = commerce.client.get("/products/" + product["id"]).json()
    assert (after["stock"], after["reserved"]) == (3, 0)
    assert commerce.pay(user, placed, key=key).status_code == 200
    paid = commerce.client.get("/store/orders/" + draft["id"], headers=user).json()
    cancelled = commerce.client.post(
        "/store/orders/" + draft["id"] + "/cancel", headers=user, json={"version": paid["version"]}
    )
    assert cancelled.status_code == 200
    assert (
        commerce.client.post(
            "/store/orders/" + draft["id"] + "/cancel",
            headers=user,
            json={"version": cancelled.json()["version"]},
        ).status_code
        == 409
    )
    restored = commerce.client.get("/products/" + product["id"]).json()
    assert (restored["stock"], restored["reserved"]) == (5, 0)
    second = commerce.draft(
        user, commerce.cart(user, [{"kind": "product", "id": product["id"], "quantity": 2}])
    )
    assert commerce.pay(user, commerce.place(user, second).json()).status_code == 201
    for action in ("approve", "ship", "deliver"):
        current = commerce.client.get("/store/orders/" + second["id"], headers=user).json()
        assert (
            commerce.client.post(
                "/store/orders/" + second["id"] + "/" + action,
                headers=commerce.admin,
                json={"version": current["version"]},
            ).status_code
            == 200
        )
    final = commerce.client.get("/products/" + product["id"]).json()
    assert (final["stock"], final["reserved"]) == (3, 0)


def test_cleanup_keeps_draft_and_order_images_and_removes_only_old_unused_uploads(commerce):
    unused = commerce.image()
    photo = commerce.image()
    draft = commerce.client.post(
        "/products",
        headers=commerce.admin,
        json={"name": "Photo draft", "images": [{"mediaId": photo["id"]}]},
    ).json()
    commerce.products.append(draft["id"])
    with commerce.scenario.database.connect() as connection:
        connection.execute(
            "UPDATE media SET created_at=CURRENT_TIMESTAMP-INTERVAL '25 hours' WHERE id=ANY(%s)",
            ([UUID(unused["id"]), UUID(photo["id"])],),
        )
    service = MediaService(
        commerce.scenario.database,
        Settings(media_root=commerce.client.app.state.controllers.media.media.root),
    )
    assert service.cleanup() == 1
    assert commerce.client.get("/media/" + unused["id"], headers=commerce.admin).status_code == 404
    assert commerce.client.get("/media/" + photo["id"], headers=commerce.admin).status_code == 200
    assert service.cleanup() == 0


def test_cleanup_and_gallery_save_never_create_a_broken_reference(commerce):
    image = commerce.image()
    with commerce.scenario.database.connect() as connection:
        connection.execute(
            "UPDATE media SET created_at=CURRENT_TIMESTAMP-INTERVAL '25 hours' WHERE id=%s",
            (UUID(image["id"]),),
        )
    settings = Settings(media_root=commerce.client.app.state.controllers.media.media.root)

    def save():
        try:
            result = CatalogService(commerce.scenario.database).save(
                ProductCommand(name="Concurrent draft", images=[{"mediaId": image["id"]}])
            )
            return result
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        saved, _ = list(
            pool.map(
                lambda operation: operation(),
                [save, lambda: MediaService(commerce.scenario.database, settings).cleanup()],
            )
        )
    if isinstance(saved, dict):
        commerce.products.append(str(saved["id"]))
        assert commerce.client.get("/media/" + image["id"], headers=commerce.admin).status_code == 200
    else:
        assert saved.code == "MEDIA_NOT_FOUND"
