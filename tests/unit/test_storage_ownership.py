import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mail_runtime", ROOT / "docker/run_mail.py")
mail_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mail_runtime)


def test_images_keep_the_legacy_application_identity():
    for filename in ("Dockerfile", "docker/Dockerfile.mail"):
        content = (ROOT / filename).read_text(encoding="utf-8")
        assert "--gid 998 petstore" in content
        assert "--uid 998 --gid petstore" in content
    entrypoint = (ROOT / "docker/entrypoint.sh").read_text(encoding="utf-8")
    assert "chown --no-dereference -R" in entrypoint
    assert "realpath -m" in entrypoint


def test_mail_repairs_only_its_storage_before_dropping_root(monkeypatch):
    calls = []
    monkeypatch.setattr(Path, "mkdir", Mock())
    monkeypatch.setattr(mail_runtime.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(
        mail_runtime.subprocess, "run", lambda command, **kwargs: calls.append(("chown", command, kwargs))
    )
    for name in ("setgroups", "setgid", "setuid"):
        monkeypatch.setattr(
            mail_runtime.os, name, lambda value, name=name: calls.append((name, value)), raising=False
        )
    mail_runtime.prepare_storage()
    assert calls == [
        ("chown", ["chown", "--no-dereference", "-R", "998:998", "/smtp4dev"], {"check": True}),
        ("setgroups", []),
        ("setgid", 998),
        ("setuid", 998),
    ]


def test_failed_ownership_repair_prevents_startup_and_privilege_changes(monkeypatch):
    monkeypatch.setattr(Path, "mkdir", Mock())
    monkeypatch.setattr(mail_runtime.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(
        mail_runtime.subprocess, "run", Mock(side_effect=subprocess.CalledProcessError(1, "chown"))
    )
    drop = Mock()
    monkeypatch.setattr(mail_runtime.os, "setuid", drop, raising=False)
    with pytest.raises(subprocess.CalledProcessError):
        mail_runtime.prepare_storage()
    drop.assert_not_called()


def test_unprivileged_mail_does_not_attempt_root_operations(monkeypatch):
    monkeypatch.setattr(Path, "mkdir", Mock())
    monkeypatch.setattr(mail_runtime.os, "geteuid", lambda: 998, raising=False)
    command = Mock()
    monkeypatch.setattr(mail_runtime.subprocess, "run", command)
    mail_runtime.prepare_storage()
    command.assert_not_called()
