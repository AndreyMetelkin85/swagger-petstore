from uuid import uuid4

import pytest
from tests.smoke.test_api_smoke import bearer, login
from tests.smoke.test_api_smoke import client as client


@pytest.fixture(scope="module")
def catalog_admin_headers(client):
    """Authorize the public image validation checks once without creating records."""
    return bearer(login(client, "admin", "admin123"))


@pytest.mark.parametrize("method,path", [("POST", "/products"), ("PUT", "/products/" + str(uuid4()))])
@pytest.mark.parametrize("stages", [["ALIEN"], ["ADULT", "ADULT"], ["ALL", "ADULT"]])
def test_published_image_rejects_invalid_age_fields(client, catalog_admin_headers, method, path, stages):
    response = client.request(
        method, path, headers=catalog_admin_headers, json={"name": "Age probe", "lifeStages": stages}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert response.json()["details"] == [{"field": "lifeStages", "message": "Invalid field value"}]
    assert "ALIEN" not in response.text


def test_published_openapi_documents_the_supported_age_enum(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert schemas["ProductCommand"]["properties"]["lifeStages"]["items"] == {
        "$ref": "#/components/schemas/LifeStage"
    }
    assert schemas["LifeStage"]["enum"] == ["YOUNG", "ADULT", "SENIOR", "ALL"]
