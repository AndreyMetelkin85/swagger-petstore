from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_default_docker_build_is_the_same_python_release():
    release = (ROOT / "Dockerfile.python").read_text(encoding="utf-8")
    assert (ROOT / "Dockerfile").read_text(encoding="utf-8") == release
    assert "python -m pip install --no-cache-dir --constraint requirements-runtime.txt ." in release
    assert "petstore-python-entrypoint" in release
    assert "tomcat" not in release.lower()


def test_publication_requires_python_tests_and_both_platform_scans():
    workflow = yaml.safe_load((ROOT / ".github/workflows/docker-security.yml").read_text())
    assert workflow["jobs"]["scan"]["strategy"]["matrix"]["arch"] == ["amd64", "arm64"]
    assert workflow["jobs"]["publish"]["needs"] == ["scan", "python-verification"]
    steps = workflow["jobs"]["publish"]["steps"]
    build = next(step for step in steps if step.get("id") == "image")
    assert build["with"]["file"] == "Dockerfile.python"
    assert build["with"]["platforms"] == "linux/amd64,linux/arm64"
    assert "sha-" in build["with"]["tags"]


def test_main_compose_healthcheck_works_without_curl_and_keeps_volume():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api = compose["services"]["petstore"]
    assert api["healthcheck"]["test"][:2] == ["CMD", "python"]
    assert api["volumes"] == ["petstore-data:/var/lib/postgresql/data"]
    assert compose["volumes"]["petstore-data"]["name"] == "${PETSTORE_DB_VOLUME:-swagger-petstore-db-data}"
    assert api["environment"]["PETSTORE_SMTP_HOST"] == "${PETSTORE_SMTP_HOST:-}"


def test_local_mail_overlay_is_opt_in_loopback_only_and_has_no_relay():
    compose = yaml.safe_load((ROOT / "docker-compose.mail.yml").read_text())
    assert compose["services"]["petstore"]["environment"]["PETSTORE_SMTP_HOST"] == "mail"
    mail = compose["services"]["mail"]
    assert all(port.startswith("127.0.0.1:") for port in mail["ports"])
    assert mail["environment"]["RelayOptions__SmtpServer"] == ""
    assert mail["environment"]["RelayOptions__AutomaticRelayExpression"] == ""


def test_build_context_excludes_secrets_and_local_database_backups():
    for name in [".dockerignore", "Dockerfile.python.dockerignore", "Dockerfile.java.dockerignore"]:
        patterns = (ROOT / name).read_text().splitlines()
        assert ".env" in patterns
        assert ".env.*" in patterns
        assert "backups" in patterns
