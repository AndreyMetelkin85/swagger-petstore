"""Ensure the offline photo package matches the agreed data and upload contract."""

import hashlib
import json

import pytest

from petstore.config import Settings
from petstore.service.demo_catalog_service import load_package


def test_photographs_and_manifest_are_complete_and_valid():
    package = load_package(Settings())
    assert len(package) == 8
    assert sum(entry.kind == "product" for entry, _ in package) == 4
    assert sum(entry.kind == "pet" for entry, _ in package) == 4
    assert sorted(float(entry.card.price) for entry, _ in package) == [
        790,
        1290,
        1490,
        3490,
        7000,
        9000,
        15000,
        18000,
    ]
    assert all(hashlib.sha256(payload).hexdigest() == entry.sha256 for entry, payload in package)
    assert all("https://" in entry.source_note for entry, _ in package)


def test_damaged_photo_is_rejected_before_population(tmp_path):
    root = tmp_path / "demo-catalog"
    root.mkdir()
    source = Settings().resources / "demo-catalog"
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / manifest[0]["file"]).write_bytes(b"damaged")
    with pytest.raises(ValueError, match="checksum"):
        load_package(Settings(resources=tmp_path))
