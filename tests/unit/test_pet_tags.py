import json
from unittest.mock import MagicMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from petstore.app import create_app
from petstore.data.database import Database
from petstore.data.pet_data import PetData
from petstore.model.enums import PetTagName
from petstore.model.requests import PetCreateRequest, PetUpdateRequest, TagCreateRequest, TagUpdateRequest
from petstore.model.responses import Tag
from petstore.service.exceptions import PetException
from petstore.service.pet_tag_service import UNKNOWN_TAG_MESSAGE, PetTagService
from petstore.service.validation_service import ValidationService


@pytest.fixture
def client(monkeypatch):
    """Предоставляет API-клиент с разрешённой ролью ADMIN без реальной PostgreSQL.

    :param monkeypatch: Фикстура для изолированной замены проверки авторизации.
    :yield: HTTP-клиент приложения с подменённым подключением к БД.
    """
    database = MagicMock(spec=Database)
    app = create_app(database=database, start_database=False)
    monkeypatch.setattr(app.state.auth, "authorize", Mock(return_value={"role": "ADMIN"}))
    with TestClient(app) as client:
        yield client


def test_tag_creation_update_and_response_models_have_distinct_fields():
    assert set(TagCreateRequest.model_fields) == {"name"}
    assert set(TagUpdateRequest.model_fields) == {"id", "name"}
    assert set(Tag.model_fields) == {"id", "name"}


def test_pet_tag_catalog_is_public_fixed_and_independent_of_database(client):
    response = client.get("/api/v3/catalog/pet-tags")
    assert response.status_code == 200
    assert response.json() == [
        {"name": "friendly", "label": "Дружелюбный"},
        {"name": "vaccinated", "label": "Привит"},
        {"name": "sterilized", "label": "Стерилизован"},
        {"name": "microchipped", "label": "Чипирован"},
    ]
    assert {tag["name"] for tag in response.json()} == {tag.value for tag in PetTagName}
    client.app.state.auth.authorize.assert_not_called()
    client.app.state.database.connect.assert_not_called()


@pytest.mark.parametrize("name", ["friendly", "vaccinated", "sterilized", "microchipped"])
def test_creation_accepts_every_tag_from_fixed_catalog(name):
    request = PetCreateRequest.model_validate({"name": "Luna", "price": "15000.00", "tags": [{"name": name}]})
    assert ValidationService.pet(request) == []


@pytest.mark.parametrize("name", ["unknown", "Friendly", "tag1", "python"])
def test_create_pet_rejects_names_outside_catalog_even_if_format_is_valid(client, name):
    response = client.post(
        "/api/v3/pet", json={"name": "Luna", "price": "15000.00", "tags": [{"name": name}]}
    )
    assert response.status_code == 422
    assert response.json()["details"] == [{"field": "tags[0].name", "message": UNKNOWN_TAG_MESSAGE}]
    client.app.state.database.connect.assert_not_called()


@pytest.mark.parametrize("value", ["10000000-0000-4000-8000-000000000099", None, "invalid-uuid", 123, {}])
def test_create_pet_rejects_client_tag_id_before_writing_to_database(client, value):
    response = client.post(
        "/api/v3/pet",
        json={"name": "Luna", "price": "15000.00", "tags": [{"id": value, "name": "friendly"}]},
    )
    assert response.status_code == 422
    assert response.json() == {
        "status": 422,
        "error": "VALIDATION_ERROR",
        "message": "Request validation failed",
        "details": [{"field": "tags[0].id", "message": "Field is not allowed for this operation"}],
    }
    client.app.state.database.connect.assert_not_called()


def test_create_pet_returns_and_persists_server_generated_tag_ids(client):
    def insert_result(query, parameters):
        """Возвращает результат INSERT с вложенными JSON, переданными репозиторием.

        :param query: SQL-команда создания питомца.
        :param parameters: Значения колонок, сформированные репозиторием.
        :return: Подменённый курсор с созданной строкой питомца.
        """
        assert "INSERT INTO pets" in query
        category, name, urls, tags, status, price = parameters
        row = {
            "id": uuid4(),
            "category_json": category,
            "name": name,
            "photo_urls_json": urls,
            "tags_json": tags,
            "status": status,
            "price": price,
            "version": 0,
        }
        return Mock(fetchone=Mock(return_value=row))

    connection = client.app.state.database.connect.return_value.__enter__.return_value
    connection.execute.side_effect = insert_result
    response = client.post(
        "/api/v3/pet",
        json={"name": "Luna", "price": "15000.00", "tags": [{"name": "friendly"}, {"name": "vaccinated"}]},
    )
    assert response.status_code == 201
    tags = response.json()["tags"]
    assert [tag["name"] for tag in tags] == ["friendly", "vaccinated"]
    assert all(UUID(tag["id"]).version == 4 for tag in tags)
    assert tags[0]["id"] != tags[1]["id"]
    assert tags == json.loads(connection.execute.call_args.args[1][3])


@pytest.mark.parametrize("payload", [{}, {"tags": None}, {"tags": []}])
def test_create_pet_still_accepts_absent_null_and_empty_tags(payload):
    request = PetCreateRequest.model_validate({"name": "Luna", "price": "15000.00"} | payload)
    assert ValidationService.pet(request) == []
    assert json.loads(PetData.nested(request)[2]) == []


def test_create_pet_does_not_reuse_id_from_an_update_model_passed_in_python():
    client_id = uuid4()
    request = PetCreateRequest(
        name="Luna", price="15000.00", tags=[TagUpdateRequest(id=client_id, name="friendly")]
    )
    tag = json.loads(PetData.nested(request)[2])[0]
    assert UUID(tag["id"]) != client_id


def test_update_pet_keeps_existing_tag_uuid_and_generates_uuid_for_new_tag():
    existing_id = uuid4()
    request = PetUpdateRequest.model_validate(
        {
            "name": "Luna",
            "price": "15000.00",
            "version": 0,
            "tags": [{"id": str(existing_id), "name": "friendly"}, {"name": "vaccinated"}],
        }
    )
    assert ValidationService.pet(request) == []
    existing, created = json.loads(PetData.nested(request)[2])
    assert existing == {"id": str(existing_id), "name": "friendly"}
    assert UUID(created["id"]).version == 4
    assert created["id"] != existing["id"]


def test_update_can_keep_an_unchanged_historical_tag_but_cannot_introduce_unknown_names():
    legacy_id = uuid4()
    request = PetUpdateRequest.model_validate(
        {
            "name": "Luna",
            "price": "15000.00",
            "version": 0,
            "tags": [{"id": str(legacy_id), "name": "tag1"}],
        }
    )
    assert ValidationService.pet(request) == []
    PetTagService.validate_existing_tags(request, [{"id": str(legacy_id), "name": "tag1"}])
    assert json.loads(PetData.nested(request)[2]) == [{"id": str(legacy_id), "name": "tag1"}]
    for existing in ([], [{"id": str(legacy_id), "name": "tag2"}], [{"id": str(uuid4()), "name": "tag1"}]):
        with pytest.raises(PetException) as caught:
            PetTagService.validate_existing_tags(request, existing)
        assert caught.value.status == 422
        assert caught.value.details == [{"field": "tags[0].name", "message": UNKNOWN_TAG_MESSAGE}]


def test_unknown_tag_without_existing_uuid_is_rejected_on_update():
    request = PetUpdateRequest.model_validate(
        {"name": "Luna", "price": "15000.00", "version": 0, "tags": [{"name": "tag1"}]}
    )
    assert ValidationService.pet(request) == [{"field": "tags[0].name", "message": UNKNOWN_TAG_MESSAGE}]


def test_swagger_separates_create_update_and_response_tag_contracts(client):
    document = client.get("/api/v3/openapi.json").json()
    schemas = document["components"]["schemas"]
    assert schemas["PetCreateRequest"]["properties"]["tags"]["items"] == {
        "$ref": "#/components/schemas/TagCreateRequest"
    }
    assert set(schemas["TagCreateRequest"]["properties"]) == {"name"}
    assert schemas["TagCreateRequest"]["additionalProperties"] is False
    assert schemas["TagCreateRequest"]["properties"]["name"] == {"$ref": "#/components/schemas/PetTagName"}
    assert schemas["PetTagName"]["enum"] == [tag.value for tag in PetTagName]
    assert schemas["PetUpdateRequest"]["properties"]["tags"]["items"] == {
        "$ref": "#/components/schemas/TagUpdateRequest"
    }
    assert set(schemas["TagUpdateRequest"]["properties"]) == {"id", "name"}
    assert schemas["Pet"]["properties"]["tags"]["items"] == {"$ref": "#/components/schemas/Tag"}
    assert schemas["Tag"]["properties"]["id"]["readOnly"] is True
    operation = document["paths"]["/pet"]["post"]
    example = operation["requestBody"]["content"]["application/json"]["examples"]["dog"]["value"]
    assert example["tags"] == [{"name": "friendly"}]
    assert operation["responses"]["422"]["content"]["application/json"]["examples"]["clientTagId"]["value"][
        "details"
    ] == [{"field": "tags[0].id", "message": "Field is not allowed for this operation"}]
