from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from petstore.app import create_app
from petstore.data.database import Database
from petstore.model.commerce import ProductCommand

STAGES = ["YOUNG", "ADULT", "SENIOR", "ALL"]
INVALID_STAGES = [["ALIEN"], ["ADULT", "ADULT"], ["ALL", "ADULT"]]


@pytest.mark.parametrize("stages", [[stage] for stage in STAGES] + [["YOUNG", "ADULT", "SENIOR"], []])
def test_supported_life_stages_are_preserved_in_drafts(stages):
    command = ProductCommand.model_validate({"name": "Feed draft", "lifeStages": stages})
    assert command.model_dump(mode="json", by_alias=True)["lifeStages"] == stages


@pytest.mark.parametrize("stages", INVALID_STAGES + [[""], [None], "ADULT", None])
def test_invalid_life_stages_report_the_age_field(stages):
    with pytest.raises(ValidationError) as error:
        ProductCommand.model_validate({"name": "Feed draft", "lifeStages": stages})
    assert all(entry["loc"] == ("lifeStages",) for entry in error.value.errors())


@pytest.fixture
def validation_client() -> Iterator[TestClient]:
    """Предоставляет TestClient для проверки транспорта без PostgreSQL.

    :return: Результат описанной проверки или подготовки тестовых данных.
    """
    app = create_app(database=Mock(spec=Database), start_database=False)
    app.state.auth.authorize = Mock(return_value={"id": uuid4(), "role": "ADMIN"})
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    "method,path", [("POST", "/products"), ("PUT", "/products/" + str(uuid4()))], ids=["create", "update"]
)
@pytest.mark.parametrize("stages", INVALID_STAGES)
def test_catalog_request_validation_returns_safe_field_errors(validation_client, method, path, stages):
    response = validation_client.request(
        method,
        "/api/v3" + path,
        headers={"Authorization": "Bearer test"},
        json={"name": "Feed draft", "lifeStages": stages},
    )
    assert response.status_code == 422, response.text
    data = response.json()
    assert data["error"] == "VALIDATION_ERROR"
    assert data["details"] == [{"field": "lifeStages", "message": "Invalid field value"}]
    assert "ALIEN" not in response.text
    validation_client.app.state.database.connect.assert_not_called()


def test_openapi_life_stages_enum_matches_native_request_validation():
    native = ProductCommand.model_json_schema(by_alias=True)
    reference = native["properties"]["lifeStages"]["items"]["$ref"].rsplit("/", 1)[1]
    assert native["$defs"][reference]["enum"] == STAGES
    document = yaml.safe_load((Path(__file__).parents[2] / "resources/openapi.yaml").read_text("utf-8"))
    schemas = document["components"]["schemas"]
    assert schemas["ProductCommand"]["properties"]["lifeStages"]["uniqueItems"] is True
    assert schemas["ProductCommand"]["properties"]["lifeStages"]["items"] == {
        "$ref": "#/components/schemas/" + reference
    }
    assert schemas[reference]["enum"] == STAGES
