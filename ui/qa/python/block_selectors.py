"""Playwright Python: choose a block by its visible name, then find an action inside it.

These locators use neither backend UUIDs nor image URLs.
Run the small isolated smoke check with: python qa/python/block_selectors.py
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


def named_block(
    page: Page, collection: str, block: str, name_field: str, name: str
) -> Locator:
    title = page.get_by_test_id(name_field).filter(
        has_text=re.compile(rf"^\s*{re.escape(name)}\s*$")
    )
    return page.get_by_test_id(collection).get_by_test_id(block).filter(has=title)


def catalog_item(page: Page, name: str) -> Locator:
    return named_block(
        page, "catalog-items", "catalog-item-card", "catalog-item-name", name
    )


def cart_item(page: Page, name: str) -> Locator:
    return named_block(page, "cart-items", "cart-item", "cart-item-name", name)


def media_photo(page: Page, description: str) -> Locator:
    preview = page.get_by_test_id("media-asset-preview").get_by_role(
        "img", name=description, exact=True
    )
    return page.get_by_test_id("media-gallery").get_by_test_id("media-asset").filter(
        has=preview
    )


def smoke() -> None:
    from playwright.sync_api import expect, sync_playwright

    base = os.environ.get("LAPKI_PREVIEW_URL", "http://127.0.0.1:8088")
    with sync_playwright() as playwright:
        channel = os.environ.get("LAPKI_BROWSER_CHANNEL", "chrome")
        browser = playwright.chromium.launch(channel=None if channel == "bundled" else channel, headless=True)
        # A fresh context keeps these guest-cart changes separate from the user's session.
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        page.goto(f"{base}/catalog")
        food = catalog_item(page, "Корм для собак")
        expect(food).to_have_count(1)
        food.get_by_test_id("catalog-item-add").click()
        expect(page.get_by_test_id("cart-count")).to_have_text("1")
        catalog_item(page, "Керамическая миска").get_by_test_id("catalog-item-add").click()
        expect(page.get_by_test_id("cart-count")).to_have_text("2")

        # Reordering the catalog does not change how we find the same named block.
        page.get_by_test_id("catalog-sort").select_option("price-down")
        expect(catalog_item(page, "Корм для собак")).to_have_count(1)
        page.get_by_test_id("open-cart").click()
        food = cart_item(page, "Корм для собак")
        bowl = cart_item(page, "Керамическая миска")
        food.get_by_test_id("cart-item-increment").click()
        expect(food.get_by_test_id("cart-item-quantity")).to_have_text("2")
        expect(bowl.get_by_test_id("cart-item-quantity")).to_have_text("1")
        food.get_by_test_id("cart-item-remove").click()
        expect(food).to_have_count(0)
        expect(bowl).to_have_count(1)

        # Identify the thumbnail inside its gallery block, regardless of the image URL.
        bowl.get_by_test_id("cart-item-link").click()
        gallery = page.get_by_test_id("product-gallery")
        thumbnail = gallery.get_by_test_id("product-gallery-thumbnail").first
        thumbnail.click()
        expect(thumbnail).to_have_attribute("aria-pressed", "true")
        expect(page.get_by_test_id("product-image").get_by_role(
            "img", name="Керамическая миска", exact=True
        )).to_be_visible()

        page.goto(f"{base}/demo")
        page.get_by_test_id("demo-admin").click()
        page.wait_for_url("**/admin")
        page.goto(f"{base}/admin/products/new")
        photo = Path(__file__).resolve().parents[2] / "public/images/pets-hero.png"
        page.get_by_test_id("media-upload-input").set_input_files([photo, photo])
        photos = page.get_by_test_id("media-gallery").get_by_test_id("media-asset")
        expect(photos).to_have_count(2)
        # Position is used here only to assign different descriptions to two new files.
        photos.nth(0).get_by_test_id("media-asset-alt").fill("Обложка корма")
        photos.nth(1).get_by_test_id("media-asset-alt").fill("Состав корма")
        media_photo(page, "Состав корма").get_by_test_id("media-asset-make-cover").click()
        expect(photos.first.get_by_role(
            "img", name="Состав корма", exact=True
        )).to_have_attribute("alt", "Состав корма")
        media_photo(page, "Обложка корма").get_by_test_id("media-asset-remove").click()
        expect(media_photo(page, "Обложка корма")).to_have_count(0)
        expect(media_photo(page, "Состав корма")).to_have_count(1)
        browser.close()
    print("PASS Python: named blocks, nested actions, sorting, quantities, removal, thumbnails, uploaded photos; no UUID selectors")


if __name__ == "__main__":
    smoke()
