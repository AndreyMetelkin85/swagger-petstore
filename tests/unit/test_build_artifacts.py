import hashlib
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, Mock
from urllib.error import URLError

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "migration_artifacts", ROOT / "docker/fetch_migration_artifacts.py"
)
artifacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifacts)


def opener(payloads):
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.side_effect = payloads
    return Mock(return_value=response)


def test_pinned_migration_hashes_do_not_change():
    assert set(artifacts.ARTIFACTS.values()) == {
        "7608c367fd8a92666d28711519599543c180298259963184ce04d2947a8f71e7",
        "48c781de87e2016e1f0d973748a27130f11643e7ac080173f40e2d9669d84be3",
        "ad24a4f51c9a2dcb397dd1f89938fdf3c38ff48f61b85c4a4edd02fe7671fdf0",
    }


def test_valid_download_has_a_timeout_and_bounded_read(monkeypatch):
    payload = b"verified"
    fake = opener([payload])
    monkeypatch.setattr(artifacts, "urlopen", fake)
    assert artifacts.fetch_verified("file.jar", hashlib.sha256(payload).hexdigest()) == payload
    assert fake.call_args.kwargs["timeout"] == 30
    fake.return_value.read.assert_called_with(artifacts.MAX_BYTES + 1)


def test_bad_cdn_response_retries_without_weakening_hash(monkeypatch):
    payload = b"verified"
    fake = opener([b" ", payload])
    sleeping = Mock()
    monkeypatch.setattr(artifacts, "urlopen", fake)
    monkeypatch.setattr(artifacts.time, "sleep", sleeping)
    assert artifacts.fetch_verified("file.jar", hashlib.sha256(payload).hexdigest()) == payload
    assert fake.call_count == 2 and sleeping.call_count == 1
    assert fake.call_args_list[0].args[0].startswith(artifacts.REPOSITORIES[0])
    assert fake.call_args_list[1].args[0].startswith(artifacts.REPOSITORIES[1])


@pytest.mark.parametrize("failure", [URLError("temporary"), OSError("network"), ValueError("hash")])
def test_permanent_download_failure_is_bounded_and_fails_closed(monkeypatch, failure):
    fake = Mock(side_effect=failure)
    sleeping = Mock()
    monkeypatch.setattr(artifacts, "urlopen", fake)
    monkeypatch.setattr(artifacts.time, "sleep", sleeping)
    with pytest.raises(RuntimeError):
        artifacts.fetch_verified("file.jar", "a" * 64)
    assert fake.call_count == 6 and sleeping.call_count == 5


def test_build_writes_only_verified_files_into_selected_directory(tmp_path, monkeypatch):
    fake = Mock(return_value=b"verified")
    monkeypatch.setattr(artifacts, "fetch_verified", fake)
    artifacts.main(tmp_path)
    assert {path.name for path in tmp_path.iterdir()} == {Path(path).name for path in artifacts.ARTIFACTS}
    assert fake.call_count == 3
