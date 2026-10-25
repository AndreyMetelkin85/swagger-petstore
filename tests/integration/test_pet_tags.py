import json
from uuid import UUID, uuid4

import pytest


def test_created_tag_can_be_read_found_and_kept_on_pet_update(scenario):
    pet = scenario.pet()
    original_tag = pet["tags"][0]
    assert UUID(original_tag["id"]).version == 4
    loaded = scenario.client.get(f"/pet/{pet['id']}")
    assert loaded.status_code == 200
    assert loaded.json()["tags"] == [original_tag]
    found = scenario.client.get("/pet/findByTags", params={"tags": original_tag["name"]})
    assert found.status_code == 200
    assert any(item["id"] == pet["id"] and item["tags"] == [original_tag] for item in found.json())
    updated = scenario.client.put(
        f"/pet/{pet['id']}",
        headers=scenario.admin,
        json={"name": pet["name"], "price": pet["price"], "version": pet["version"], "tags": [original_tag]},
    )
    assert updated.status_code == 200
    assert updated.json()["tags"] == [original_tag]
    assert scenario.client.get(f"/pet/{pet['id']}").json()["tags"] == [original_tag]


@pytest.mark.parametrize("tag_id", ["10000000-0000-4000-8000-000000000099", None, "invalid-uuid"])
def test_client_cannot_assign_tag_uuid_when_creating_pet(scenario, tag_id):
    response = scenario.client.post(
        "/pet",
        headers=scenario.admin,
        json={"name": "Invalid tag UUID", "price": "10.25", "tags": [{"id": tag_id, "name": "friendly"}]},
    )
    if response.status_code == 201:
        scenario.pets.append(UUID(response.json()["id"]))
    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert response.json()["details"] == [
        {"field": "tags[0].id", "message": "Field is not allowed for this operation"}
    ]


def test_existing_historical_tags_remain_readable_and_editable_without_migration(scenario):
    pet = scenario.pet()
    legacy_tag = {"id": pet["tags"][0]["id"], "name": "tag1"}
    with scenario.database.connect() as connection:
        connection.execute(
            "UPDATE pets SET tags_json = %s WHERE id = %s", (json.dumps([legacy_tag]), pet["id"])
        )
    assert scenario.client.get(f"/pet/{pet['id']}").json()["tags"] == [legacy_tag]
    payload = {"name": pet["name"], "price": pet["price"], "version": pet["version"], "tags": [legacy_tag]}
    updated = scenario.client.put(f"/pet/{pet['id']}", headers=scenario.admin, json=payload)
    assert updated.status_code == 200
    assert updated.json()["tags"] == [legacy_tag]
    payload["version"] = updated.json()["version"]
    payload["tags"] = [{"id": legacy_tag["id"], "name": "unknown-new-tag"}]
    rejected = scenario.client.put(f"/pet/{pet['id']}", headers=scenario.admin, json=payload)
    assert rejected.status_code == 422
    assert scenario.client.get(f"/pet/{pet['id']}").json()["tags"] == [legacy_tag]
