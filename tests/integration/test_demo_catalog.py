"""Exercise additive startup with real PostgreSQL and bundled photographs."""

from dataclasses import replace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from petstore.app import create_app
from petstore.model.commerce import ProductCommand, StockCommand
from petstore.service.catalog_service import CatalogService
from petstore.service.demo_catalog_service import STATE_FILE, populate_demo_catalog
from petstore.service.media_service import MediaService

pytestmark = pytest.mark.integration


@pytest.fixture
def photo_catalog(integration_database, tmp_path):
    """Подготавливает фотокаталог в выделенной базе и временном каталоге.

    :param integration_database: Настройки и соединение только выделенной тестовой базы.
    :param tmp_path: Временный каталог текущего теста.
    :return: Результат подготовленного тестового действия; фикстура предоставляет его через yield.
    """
    settings, database = integration_database
    settings = replace(settings, media_root=tmp_path, demo_catalog=False)
    with TestClient(create_app(settings, database), base_url="http://testserver/api/v3") as client:
        with database.connect() as connection:
            original_categories = {
                row["id"] for row in connection.execute("SELECT id FROM catalog_categories")
            }
            counts = connection.execute(
                "SELECT (SELECT count(*) FROM users) AS users,(SELECT count(*) FROM store_orders) AS orders"
            ).fetchone()
        states = []
        yield settings, database, client, counts, states
        # Удаляем только записи этого пакета в отдельной тестовой базе, не существующий каталог.
        with database.connect() as connection:
            for state in states:
                for key, identifier in state.entries.items():
                    table = "products" if key in {"cat-food", "dog-food", "bowls", "bed"} else "pets"
                    if table == "products":
                        connection.execute("DELETE FROM stock_adjustments WHERE product_id=%s", (identifier,))
                    column = "product_id" if table == "products" else "pet_id"
                    connection.execute(f"DELETE FROM catalog_images WHERE {column}=%s", (identifier,))
                    connection.execute(f"DELETE FROM {table} WHERE id=%s", (identifier,))
            connection.execute(
                "DELETE FROM media WHERE source_note LIKE 'lapki-photo-catalog-v1:%' "
                "AND NOT EXISTS (SELECT 1 FROM catalog_images WHERE media_id=media.id) "
                "AND NOT EXISTS (SELECT 1 FROM order_lines WHERE cover_id=media.id)"
            )
            for row in connection.execute("SELECT id FROM catalog_categories").fetchall():
                if row["id"] not in original_categories:
                    connection.execute("DELETE FROM catalog_categories WHERE id=%s", (row["id"],))


def test_repeat_and_journal_recovery_preserve_edits_and_archives(photo_catalog):
    settings, database, client, before, states = photo_catalog
    state = populate_demo_catalog(database, settings)
    states.append(state)
    assert len(state.entries) == 8 and state.completed
    service = CatalogService(database)
    media = MediaService(database, settings)
    for key, identifier in state.entries.items():
        kind = "product" if key in {"cat-food", "dog-food", "bowls", "bed"} else "pet"
        card = service.get(kind, identifier, True)
        assert card["publicationStatus"] == "PUBLISHED" and len(card["images"]) == 1
        image_id = UUID(str(card["images"][0]["mediaId"]))
        assert media.get(image_id, None, False)[0][:2] == b"\xff\xd8"
        assert media.get(image_id, None, True)[0][:2] == b"\xff\xd8"
        assert media.get(image_id, None)["sourceType"] == "DEMO"
    product = service.get("product", state.entries["cat-food"], False)
    # Внешние имена полей явные; серверные поля не входят в команду.
    command = {
        "name": "Изменено учеником",
        "sku": product["sku"],
        "description": "Мой каталог",
        "categoryId": product["categoryId"],
        "brand": "Учебный бренд",
        "productType": "FEED",
        "animalTypes": ["cat"],
        "price": 321,
        "feedForm": "DRY",
        "lifeStages": ["ADULT"],
        "netWeightGrams": 1000,
        "version": product["version"],
        "images": [{"mediaId": product["images"][0]["mediaId"], "isCover": True}],
    }
    changed = service.save(ProductCommand.model_validate(command), product["id"])
    with database.connect() as connection:
        actor = connection.execute("SELECT id,role FROM users WHERE role='ADMIN' LIMIT 1").fetchone()
    changed = service.adjust_stock(
        changed["id"], StockCommand(version=changed["version"], delta=-3, reason="Учебное изменение"), actor
    )
    pet = service.get("pet", state.entries["barsik"], False)
    service.publish("pet", pet["id"], pet["version"], "ARCHIVED")
    assert populate_demo_catalog(database, settings).entries == state.entries
    (settings.media_root / STATE_FILE).unlink()
    recovered = populate_demo_catalog(database, settings)
    assert recovered.entries == state.entries
    assert service.get("product", changed["id"], False)["price"] == 321
    assert service.get("product", changed["id"], False)["stock"] == 7
    assert service.get("pet", pet["id"], False)["publicationStatus"] == "ARCHIVED"
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT (SELECT count(*) FROM users) AS users,(SELECT count(*) FROM store_orders) AS orders"
            ).fetchone()
            == before
        )
        assert (
            connection.execute(
                "SELECT count(*) AS total FROM media WHERE source_note LIKE 'lapki-photo-catalog-v1:%'"
            ).fetchone()["total"]
            == 8
        )


def test_failed_population_rolls_back_and_can_resume(photo_catalog, monkeypatch):
    settings, database, _, _, states = photo_catalog
    original = CatalogService.publish
    calls = 0

    def fail_second(self, *args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Interrupted startup")
        return original(self, *args)

    with monkeypatch.context() as patch:
        patch.setattr(CatalogService, "publish", fail_second)
        with pytest.raises(RuntimeError, match="Interrupted startup"):
            populate_demo_catalog(database, settings)
    assert not list(settings.media_root.glob("*.jpg"))
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT count(*) AS total FROM media WHERE source_note LIKE 'lapki-photo-catalog-v1:%'"
            ).fetchone()["total"]
            == 0
        )
    state = populate_demo_catalog(database, settings)
    states.append(state)
    assert len(state.entries) == 8


def test_disabled_startup_leaves_catalog_untouched(photo_catalog):
    settings, _, client, _, _ = photo_catalog
    assert client.get("/products", params={"q": "LAPKI-DEMO-V1"}).json()["total"] == 0
    assert not (settings.media_root / STATE_FILE).exists()
