"""Check bundled demo photographs on the isolated default-mode container."""

import json
import os

import httpx
import pytest
from playwright.sync_api import sync_playwright

from petstore.config import Settings

pytestmark = [pytest.mark.system, pytest.mark.ui]


def test_default_catalog_photographs_filters_and_guest_cart():
    url = os.getenv("PETSTORE_DEMO_STORE_URL")
    if not url:
        pytest.skip("Set PETSTORE_DEMO_STORE_URL for the isolated photo-enabled image")
    manifest = json.loads((Settings().resources / "demo-catalog/manifest.json").read_text(encoding="utf-8"))
    products = httpx.get(url + "/api/v3/products", params={"pageSize": 100}).json()["items"]
    pets = httpx.get(url + "/api/v3/catalog/pets", params={"pageSize": 100}).json()["items"]
    cards = [
        next(row for row in products + pets if row["name"] == entry["card"]["name"]) for entry in manifest
    ]
    assert all(card["publicationStatus"] == "PUBLISHED" and card["images"] for card in cards)
    with sync_playwright() as runner:
        browser = runner.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE"))
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        for card in cards:
            page.goto(url + "/catalog/" + card["id"])
            image = page.get_by_test_id("product-image").locator("img")
            image.wait_for()
            image.evaluate("image => image.decode()")
            assert image.evaluate("image => image.naturalWidth > 0")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.set_viewport_size({"width": 1440, "height": 1000})
        for species in ("cat", "dog"):
            page.goto(url + "/pets?animal=" + species)
            page.get_by_test_id("catalog-item-card").first.wait_for()
            for card in [record for record in cards if record.get("animalType") == species]:
                block = page.locator('[data-testid="catalog-item-card"][data-item-id="' + card["id"] + '"]')
                image = block.locator("img")
                image.wait_for()
                image.evaluate("image => image.decode()")
        page.goto(url + "/catalog")
        block = page.locator('[data-testid="catalog-item-card"][data-item-id="' + cards[0]["id"] + '"]')
        block.get_by_test_id("catalog-item-add").click()
        page.goto(url + "/cart")
        image = page.get_by_test_id("cart-item").locator("img").first
        image.wait_for()
        image.evaluate("image => image.decode()")
        browser.close()
