from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb
from tests.integration.test_commerce import commerce as commerce

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("stage", ["YOUNG", "ADULT", "SENIOR", "ALL"])
def test_supported_age_round_trips_through_draft_update_and_feed_publication(commerce, stage):
    response = commerce.client.post(
        "/products", headers=commerce.admin, json={"name": "Feed draft", "lifeStages": [stage]}
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    commerce.products.append(draft["id"])
    assert draft["lifeStages"] == [stage]
    category, photo = commerce.category(), commerce.image()
    payload = {
        "version": draft["version"],
        "name": "Complete feed",
        "sku": uuid4().hex,
        "productType": "FEED",
        "brand": "Test",
        "animalTypes": ["cat"],
        "categoryId": category["id"],
        "price": 100,
        "feedForm": "DRY",
        "lifeStages": [stage],
        "netWeightGrams": 1000,
        "images": [{"mediaId": photo["id"]}],
    }
    updated = commerce.client.put("/products/" + draft["id"], headers=commerce.admin, json=payload)
    assert updated.status_code == 200, updated.text
    published = commerce.client.post(
        "/products/" + draft["id"] + "/publish",
        headers=commerce.admin,
        json={"version": updated.json()["version"]},
    )
    assert published.status_code == 200, published.text
    assert published.json()["lifeStages"] == [stage]
    assert commerce.client.get("/products/" + draft["id"]).json()["lifeStages"] == [stage]
    replaced = commerce.client.put(
        "/products/" + draft["id"],
        headers=commerce.admin,
        json=payload | {"version": published.json()["version"]},
    )
    assert replaced.status_code == 200 and replaced.json()["lifeStages"] == [stage]


@pytest.mark.parametrize("stages", [["ALIEN"], ["ADULT", "ADULT"], ["ALL", "ADULT"]])
def test_invalid_age_cannot_create_or_replace_a_feed_and_preserves_the_card(commerce, stages):
    product, payload = commerce.product()
    for request in ({"name": "Partial draft", "lifeStages": stages}, payload | {"lifeStages": stages}):
        created = commerce.client.post("/products", headers=commerce.admin, json=request)
        assert created.status_code == 422, created.text
        assert created.json()["error"] == "VALIDATION_ERROR"
        assert created.json()["details"] == [{"field": "lifeStages", "message": "Invalid field value"}]
    for status in ("PUBLISHED", "DRAFT"):
        replaced = commerce.client.put(
            "/products/" + product["id"],
            headers=commerce.admin,
            json=payload | {"version": product["version"], "lifeStages": stages},
        )
        assert replaced.status_code == 422, replaced.text
        assert replaced.json()["error"] == "VALIDATION_ERROR"
        assert replaced.json()["details"] == [{"field": "lifeStages", "message": "Invalid field value"}]
        assert (
            commerce.client.get("/admin/products/" + product["id"], headers=commerce.admin).json() == product
        )
        if status == "PUBLISHED":
            unpublished = commerce.client.post(
                "/products/" + product["id"] + "/unpublish",
                headers=commerce.admin,
                json={"version": product["version"]},
            )
            assert unpublished.status_code == 200
            product = unpublished.json()


def test_legacy_invalid_age_is_editable_but_cannot_be_published_until_repaired(commerce):
    product, payload = commerce.product()
    unpublished = commerce.client.post(
        "/products/" + product["id"] + "/unpublish",
        headers=commerce.admin,
        json={"version": product["version"]},
    )
    assert unpublished.status_code == 200
    with commerce.scenario.database.connect() as connection:
        connection.execute(
            "UPDATE products SET life_stages=%s WHERE id=%s", (Jsonb(["ALIEN"]), product["id"])
        )
    before = commerce.client.get("/admin/products/" + product["id"], headers=commerce.admin)
    assert before.status_code == 200 and before.json()["lifeStages"] == ["ALIEN"]
    rejected = commerce.client.post(
        "/products/" + product["id"] + "/publish",
        headers=commerce.admin,
        json={"version": before.json()["version"]},
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"] == "VALIDATION_ERROR"
    assert rejected.json()["details"] == [{"field": "lifeStages", "message": "Invalid field value"}]
    assert "ALIEN" not in rejected.text
    assert (
        commerce.client.get("/admin/products/" + product["id"], headers=commerce.admin).json()
        == before.json()
    )
    repaired = commerce.client.put(
        "/products/" + product["id"],
        headers=commerce.admin,
        json=payload | {"version": before.json()["version"]},
    )
    assert repaired.status_code == 200 and repaired.json()["lifeStages"] == ["ADULT"]
    assert (
        commerce.client.post(
            "/products/" + product["id"] + "/publish",
            headers=commerce.admin,
            json={"version": repaired.json()["version"]},
        ).status_code
        == 200
    )
