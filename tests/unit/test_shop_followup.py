import io
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from petstore.app import create_app
from petstore.config import Settings
from petstore.data.database import Database
from petstore.model.commerce import PetCardCommand, ProductCommand, TelemetryEvent
from petstore.service.catalog_service import CatalogService
from petstore.service.exceptions import ApiException
from petstore.service.media_service import normalize_image
from petstore.testing import require_test_database, verify_connected_database


@pytest.mark.parametrize("command", [ProductCommand(name="Draft"), PetCardCommand(name="Draft")])
def test_draft_has_no_invented_price_and_publication_lists_missing_fields(command):
    assert command.price is None
    with pytest.raises(ApiException) as error:
        CatalogService.publication_fields(command, False)
    assert error.value.code == "PUBLICATION_INCOMPLETE"
    assert {"categoryId", "price", "images"} <= {detail["field"] for detail in error.value.details}


def test_feed_composition_is_optional_but_brand_age_form_and_weight_are_required():
    command = ProductCommand(
        name="Feed",
        sku="F",
        price=1,
        category_id=uuid4(),
        animal_types=["cat"],
        product_type="FEED",
        brand="Brand",
        feed_form="DRY",
        life_stages=["ALL"],
        net_weight_grams=100,
    )
    CatalogService.publication_fields(command, True)
    with pytest.raises(ValueError):
        ProductCommand(name="Feed", life_stages=["ALL", "ADULT"])


@pytest.mark.parametrize("format", ["PNG", "WEBP", "JPEG"])
def test_images_are_jpeg_with_bounded_dimensions_and_no_metadata(format):
    payload = io.BytesIO()
    image = (
        Image.new("RGBA", (2000, 1000), (200, 0, 0, 0))
        if format != "JPEG"
        else Image.new("RGB", (2000, 1000), "red")
    )
    image.save(payload, format=format)
    photo, thumb, mime, width, height = normalize_image(payload.getvalue())
    assert (mime, width, height) == ("image/jpeg", 1600, 800)
    with Image.open(io.BytesIO(photo)) as decoded:
        assert decoded.format == "JPEG" and not decoded.getexif()
        if format != "JPEG":
            assert decoded.getpixel((0, 0)) == (255, 255, 255)
    with Image.open(io.BytesIO(thumb)) as decoded:
        assert decoded.format == "JPEG" and decoded.size == (400, 200)


@pytest.mark.parametrize(
    "enabled,name",
    [(False, "petstore_python_test"), (True, "petstore"), (True, "production"), (True, "petstore_backup")],
)
def test_reset_and_clock_support_fail_closed_for_regular_databases(enabled, name):
    with pytest.raises(ValueError):
        require_test_database(Settings(test_support=enabled, db_url="postgresql://localhost/" + name))


def test_declared_test_url_cannot_hide_an_actual_production_connection():
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {"name": "petstore"}
    with pytest.raises(ValueError):
        verify_connected_database(
            connection, Settings(test_support=True, db_url="postgresql://localhost/petstore_training")
        )
    assert connection.execute.call_count == 1


def test_telemetry_logs_safe_correlation_and_server_actor_without_private_input(caplog):
    app = create_app(database=Mock(spec=Database), start_database=False)
    actor = uuid4()
    app.state.auth.authorize = Mock(return_value={"id": actor, "role": "USER"})
    caplog.set_level("INFO", logger="petstore.telemetry")
    request_id = str(uuid4())
    payload = {
        "event": "api_failure",
        "requestId": request_id,
        "errorCode": "CART_VERSION_CONFLICT",
        "resourceId": str(uuid4()),
        "routeId": "/checkout",
        "endpointTemplate": "/store/orders/:id/place",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v3/telemetry/client-events",
                json={"events": [payload]},
                headers={"Authorization": "Bearer test"},
            ).status_code
            == 204
        )
        for patch in (
            {"errorCode": "PRIVATEPASSWORD"},
            {"routeId": "/private-person"},
            {"endpointTemplate": "/users/email@example.com"},
            {"password": "NeverLogPassword"},
            {"actorId": str(uuid4())},
        ):
            assert (
                client.post("/api/v3/telemetry/client-events", json={"events": [payload | patch]}).status_code
                == 422
            )
    assert request_id in caplog.text and str(actor) in caplog.text
    for secret in ("PRIVATEPASSWORD", "private-person", "email@example.com", "NeverLogPassword"):
        assert secret not in caplog.text
    with pytest.raises(ValueError):
        TelemetryEvent(event="navigation", timestamp="2026-10-07T00:00:00")
