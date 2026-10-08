"""Contract caching cannot leak app mutations or retain an edited file."""

import shutil
from pathlib import Path
from unittest.mock import Mock

from petstore.app import _load_contract, create_app
from petstore.config import Settings
from petstore.data.database import Database


def test_instances_have_independent_contracts_and_reuse_safe_parse():
    _load_contract.cache_clear()
    first = create_app(database=Mock(spec=Database), start_database=False)
    first.state.document["info"]["title"] = "Changed only in this instance"
    second = create_app(database=Mock(spec=Database), start_database=False)
    assert second.state.document["info"]["title"] != first.state.document["info"]["title"]
    assert _load_contract.cache_info().misses == 1
    assert _load_contract.cache_info().hits == 1


def test_changed_contract_file_is_reloaded(tmp_path: Path):
    path = tmp_path / "openapi.yaml"
    shutil.copy2(Settings().resources / "openapi.yaml", path)
    _load_contract.cache_clear()
    before = _load_contract(path, path.stat().st_mtime_ns, path.stat().st_size)
    path.write_text(path.read_text(encoding="utf-8") + "\nx-cache-test: changed\n", encoding="utf-8")
    after = _load_contract(path, path.stat().st_mtime_ns, path.stat().st_size)
    assert "x-cache-test" not in before
    assert after["x-cache-test"] == "changed"
