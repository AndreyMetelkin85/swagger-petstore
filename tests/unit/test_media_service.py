import io
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from PIL import Image

from petstore.config import Settings
from petstore.data.catalog_data import CatalogData
from petstore.service.exceptions import ApiException
from petstore.service.media_service import MediaService, normalize_image


def image_bytes(format="PNG"):
    data = io.BytesIO()
    Image.new("RGB", (8, 4)).save(data, format=format)
    return data.getvalue()


@pytest.fixture
def media(tmp_path):
    database = MagicMock()
    connection = database.connect.return_value.__enter__.return_value
    identifier = uuid4()
    row = {
        "id": identifier,
        "mime_type": "image/png",
        "width": 8,
        "height": 4,
        "size_bytes": 100,
        "source_type": "OWN",
        "source_note": "",
        "created_at": None,
    }
    connection.execute.return_value.fetchone.return_value = row
    return MediaService(database, Settings(media_root=tmp_path)), connection, row


def test_verified_upload_and_private_storage_names(media):
    service, connection, row = media
    actor = {"id": uuid4(), "role": "ADMIN"}
    result = service.upload(image_bytes(), "OWN", "", actor)
    assert result["mime"] == "image/png" and result["width"] == 8
    paths = list(service.root.iterdir())
    assert len(paths) == 2 and all(p.suffix == ".png" for p in paths)
    assert not {"created_by", "path", "password"} & result.keys()


def test_failed_database_insert_removes_only_new_upload_files(media):
    service, connection, _ = media
    unrelated = service.root / "do-not-touch.txt"
    unrelated.touch()
    connection.execute.side_effect = RuntimeError("database error")
    with pytest.raises(RuntimeError):
        service.upload(image_bytes(), "DEMO", "", {"id": uuid4()})
    assert list(service.root.iterdir()) == [unrelated]


def test_storage_failure_is_safe_service_error(media, monkeypatch):
    service, _, _ = media
    monkeypatch.setattr(type(service.root), "open", Mock(side_effect=OSError("private path")))
    with pytest.raises(ApiException) as failure:
        service.upload(image_bytes(), "SUPPLIER", "Supplier", {"id": uuid4()})
    assert failure.value.code == "MEDIA_STORAGE_UNAVAILABLE"
    assert "private path" not in failure.value.message


@pytest.mark.parametrize("source,note", [("OTHER", ""), ("OWN", "a" * 1001)], ids=["source", "note"])
def test_source_validation_precedes_file_writes(media, source, note):
    service, _, _ = media
    with pytest.raises(ApiException):
        service.upload(image_bytes(), source, note, {"id": uuid4()})
    assert not list(service.root.iterdir())


def test_get_admin_metadata_file_and_missing_storage(media):
    service, _, row = media
    admin = {"role": "ADMIN"}
    assert service.get(row["id"], admin)["id"] == row["id"]
    service.path(row["id"], row["mime_type"]).touch()
    assert service.get(row["id"], admin, False) == (b"", "image/png")
    with pytest.raises(ApiException) as failure:
        service.get(row["id"], admin, True)
    assert failure.value.code == "MEDIA_STORAGE_UNAVAILABLE"


def test_nonexistent_and_private_media_are_not_disclosed(media):
    service, connection, row = media
    connection.execute.return_value.fetchone.return_value = None
    with pytest.raises(ApiException) as failure:
        service.get(row["id"], None)
    assert failure.value.code == "MEDIA_NOT_FOUND"
    connection.execute.return_value.fetchone.side_effect = [row, None]
    with pytest.raises(ApiException):
        service.get(row["id"], None)


def test_visibility_public_owned_and_foreign_covers(media):
    service, connection, row = media
    connection.execute.return_value.fetchone.side_effect = [None, {"exists": 1}, None, None]
    assert service.visible(connection, row["id"], {"id": uuid4(), "role": "USER"})
    assert not service.visible(connection, row["id"], {"id": uuid4(), "role": "USER"})


def test_delete_unused_files_tombstones_and_reference_guards(media):
    service, connection, row = media
    for thumbnail in (True, False):
        service.path(row["id"], row["mime_type"], thumbnail).touch()
    connection.execute.return_value.fetchone.side_effect = [row, None]
    service.delete(row["id"])
    assert not list(service.root.iterdir())
    connection.execute.return_value.fetchone.side_effect = [row, {"used": 1}]
    with pytest.raises(ApiException) as failure:
        service.delete(row["id"])
    assert failure.value.code == "MEDIA_IN_USE"
    connection.execute.return_value.fetchone.side_effect = [None]
    with pytest.raises(ApiException) as failure:
        service.delete(row["id"])
    assert failure.value.code == "MEDIA_NOT_FOUND"


def test_invalid_persisted_mime_cannot_become_a_path(media):
    service, _, row = media
    with pytest.raises(ApiException):
        service.path(row["id"], "../../private")


def test_worker_capacity_format_and_pixel_limits(monkeypatch):
    semaphore = Mock()
    semaphore.acquire.return_value = False
    monkeypatch.setattr("petstore.service.media_service.IMAGE_WORKERS", semaphore)
    with pytest.raises(ApiException) as failure:
        normalize_image(image_bytes())
    assert failure.value.status == 503
    semaphore.release.assert_not_called()
    semaphore.acquire.return_value = True
    with pytest.raises(ApiException) as failure:
        normalize_image(image_bytes("GIF"))
    assert failure.value.code == "INVALID_IMAGE_FORMAT"
    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.format = "PNG"
    probe.size = (10000, 10000)
    monkeypatch.setattr("petstore.service.media_service.Image.open", Mock(return_value=probe))
    with pytest.raises(ApiException) as failure:
        normalize_image(b"bounded header")
    assert failure.value.status == 413


def test_catalog_table_and_optimistic_version_guards():
    assert CatalogData.table("pet") == "pets"
    with pytest.raises(ApiException):
        CatalogData.table("users; DROP")
    with pytest.raises(ApiException) as failure:
        CatalogData.version({"version": 1}, None)
    assert failure.value.details == [{"field": "version", "message": "Version is required"}]
    with pytest.raises(ApiException) as failure:
        CatalogData.version({"version": 1}, 0, "ORDER_VERSION_CONFLICT")
    assert failure.value.code == "ORDER_VERSION_CONFLICT"


def test_extreme_image_dimensions_keep_the_oversize_error(monkeypatch):
    monkeypatch.setattr(
        "petstore.service.media_service.Image.open",
        Mock(side_effect=Image.DecompressionBombError("Private metadata")),
    )
    with pytest.raises(ApiException) as failure:
        normalize_image(b"bounded input")
    assert failure.value.status == 413 and failure.value.code == "IMAGE_TOO_LARGE"
