import io
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import ValidationError

from petstore.model.commerce import CartCommand, PetCardCommand, ProductCommand
from petstore.service.exceptions import ApiException
from petstore.service.media_service import MAX_BYTES, normalize_image
from petstore.utils.responses import public_delivery


def encoded(format="PNG", metadata=False):
    image = Image.new("RGB", (32, 20), "red")
    data = io.BytesIO()
    arguments = {}
    if metadata:
        exif = Image.Exif()
        exif[315] = "Private camera owner"
        exif[274] = 6
        arguments["exif"] = exif.tobytes()
    image.save(data, format=format, **arguments)
    return data.getvalue()


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
def test_valid_image_content_is_normalized_with_thumbnail(format):
    image, thumb, mime, width, height = normalize_image(encoded(format))
    assert mime.startswith("image/")
    assert (width, height) == (32, 20)
    with Image.open(io.BytesIO(image)) as result:
        assert not result.getexif()
        assert result.n_frames == 1 if hasattr(result, "n_frames") else True
    with Image.open(io.BytesIO(thumb)) as result:
        assert result.width <= 480 and result.height <= 480


def test_exif_is_removed_and_orientation_applied():
    image, _, _, width, height = normalize_image(encoded("JPEG", metadata=True))
    assert (width, height) == (20, 32)
    with Image.open(io.BytesIO(image)) as result:
        assert not result.getexif()
    assert b"Private camera owner" not in image


@pytest.mark.parametrize(
    "payload",
    [b"", b"not an image", b"<svg/>", b"a" * (MAX_BYTES + 1)],
    ids=["empty", "garbage", "svg", "oversize"],
)
def test_invalid_images_never_pass_content_verification(payload):
    with pytest.raises(ApiException):
        normalize_image(payload)


def test_static_only_webp():
    result = io.BytesIO()
    frames = [Image.new("RGB", (10, 10), color) for color in ("red", "blue")]
    frames[0].save(result, format="WEBP", save_all=True, append_images=frames[1:], duration=100)
    with pytest.raises(ApiException) as failure:
        normalize_image(result.getvalue())
    assert failure.value.code == "ANIMATED_IMAGE_NOT_ALLOWED"


@pytest.mark.parametrize("price", ["0", "-1", "1.001", "NaN", "Infinity", "10000000000"])
def test_money_constraints(price):
    with pytest.raises(ValidationError):
        ProductCommand(sku="SKU", name="Product", price=price)


def test_feed_requires_form_weight_and_ingredients():
    with pytest.raises(ValidationError):
        ProductCommand(sku="FEED", name="Feed", price=Decimal("1"), productType="FEED")


def test_gallery_unique_ids_one_cover_and_limit():
    identifier = uuid4()
    for images in (
        [{"mediaId": identifier}, {"mediaId": identifier}],
        [{"mediaId": uuid4(), "isCover": True}, {"mediaId": uuid4(), "isCover": True}],
        [{"mediaId": uuid4()} for _ in range(21)],
    ):
        with pytest.raises(ValidationError):
            ProductCommand(sku="SKU", name="Product", price=1, images=images)


def test_pet_birth_date_cannot_be_future():
    with pytest.raises(ValidationError):
        PetCardCommand(name="Pet", price=1, birthDate=date.today() + timedelta(days=1))


def test_cart_quantities_duplicates_and_totals_are_not_client_controlled():
    identifier = uuid4()
    with pytest.raises(ValidationError):
        CartCommand(version=1, lines=[{"kind": "pet", "id": identifier, "quantity": 2}])
    with pytest.raises(ValidationError):
        CartCommand(version=1, lines=[{"kind": "product", "id": identifier, "quantity": 1}] * 2)
    with pytest.raises(ValidationError):
        CartCommand(version=1, lines=[], total=Decimal("100"))


def test_legacy_delivery_serialization_does_not_mutate_persisted_snapshot():
    snapshot = {
        "firstName": "Buyer",
        "lastName": "Test",
        "phone": "+79991234567",
        "address": {
            "city": "Test",
            "street": "Test",
            "house": "1",
            "postalCode": "123456",
            "apartment": None,
        },
    }
    result = public_delivery(snapshot)
    assert "apartment" not in result["address"]
    assert snapshot["address"]["apartment"] is None
    assert public_delivery(None) is None
    snapshot["address"]["apartment"] = "12"
    assert public_delivery(snapshot) == snapshot
