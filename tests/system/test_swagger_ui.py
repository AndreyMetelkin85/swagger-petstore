import os

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = [pytest.mark.system, pytest.mark.ui]


def test_every_operation_has_try_out_execute_and_only_real_parameters():
    url = os.getenv("PETSTORE_UI_URL")
    if not url:
        pytest.skip("Set PETSTORE_UI_URL to an isolated test Swagger")
    spec = httpx.get(url.rstrip("/") + "/api/v3/openapi.json").json()
    operations = [
        (path, item, method, operation)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in {"get", "post", "put", "delete", "patch"}
    ]
    with sync_playwright() as playwright:
        executable = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        browser = playwright.chromium.launch(executable_path=executable)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.locator(".opblock").first.wait_for()
        expect(page.locator(".opblock")).to_have_count(len(operations))
        for path, item, method, operation in operations:
            tag = operation["tags"][0].replace(" ", "_")
            block = page.locator("[id='operations-" + tag + "-" + operation["operationId"] + "']")
            assert block.count() == 1, operation["operationId"]
            block.locator(".opblock-summary").click()
            button = block.locator(".try-out__btn")
            button.wait_for(state="visible")
            assert button.is_visible(), operation["operationId"]
            actual_parameters = item.get("parameters", []) + operation.get("parameters", [])
            if actual_parameters:
                assert block.locator(".parameters-container").is_visible(), operation["operationId"]
                assert block.locator(".parameters-container .parameter__name").count() == len(
                    actual_parameters
                )
            else:
                assert block.locator(".parameters-container:visible").count() == 0, operation["operationId"]
                assert (
                    block.locator(
                        ".opblock-section.empty-parameters > .opblock-section-header:first-child h4:visible"
                    ).count()
                    == 0
                )
                assert block.get_by_text("No parameters", exact=True).is_visible() is False
            if "requestBody" in operation:
                assert block.get_by_text("Request body", exact=True).is_visible()
            button.click()
            block.locator(".execute").wait_for(state="visible")
            assert block.locator(".execute").is_visible(), operation["operationId"]
            if path == "/health" and method == "get":
                block.locator(".execute").click()
                block.locator(".live-responses-table").wait_for()
                expect(block.locator(".live-responses-table")).to_contain_text('"UP"')
            block.locator(".opblock-summary").click()
            expect(block.locator(".execute")).not_to_be_visible()
        browser.close()
