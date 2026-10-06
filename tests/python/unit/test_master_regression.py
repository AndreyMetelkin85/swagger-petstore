from pathlib import Path

import yaml

from petstore.config import Settings


def test_removed_confirmation_conflict_is_absent_from_implementation_and_contract():
    root = Path(__file__).resolve().parents[3]
    assert "CONFIRMATION_STATE_CHANGED" not in (root / "python/petstore/service/auth_service.py").read_text()
    assert "CONFIRMATION_STATE_CHANGED" not in (Settings().resources / "openapi.yaml").read_text(
        encoding="utf-8"
    )


def test_swagger_has_no_malformed_json_examples_but_keeps_other_400_errors():
    spec = yaml.safe_load((Settings().resources / "openapi.yaml").read_text(encoding="utf-8"))
    checked = 0
    for item in spec["paths"].values():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            examples = (
                operation.get("responses", {})
                .get("400", {})
                .get("content", {})
                .get("application/json", {})
                .get("examples", {})
            )
            assert "malformedJson" not in examples
            if "requestBody" in operation:
                assert "missingBody" in examples
                checked += 1
    assert checked == 12
