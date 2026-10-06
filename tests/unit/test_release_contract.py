from pathlib import Path

import yaml

from petstore.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_dockerfile_builds_the_python_application():
    release = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert not (ROOT / "Dockerfile.python").exists()
    assert "python -m pip install --no-cache-dir --constraint requirements-runtime.txt ." in release
    assert "petstore-entrypoint" in release
    assert "tomcat" not in release.lower()


def test_publication_requires_python_tests_and_both_platform_scans():
    workflow = yaml.safe_load((ROOT / ".github/workflows/docker-security.yml").read_text())
    assert workflow["jobs"]["scan"]["strategy"]["matrix"]["arch"] == ["amd64", "arm64"]
    assert workflow["jobs"]["publish"]["needs"] == ["scan", "python-verification"]
    steps = workflow["jobs"]["publish"]["steps"]
    build = next(step for step in steps if step.get("id") == "image")
    assert build["with"]["file"] == "Dockerfile"
    assert build["with"]["platforms"] == "linux/amd64,linux/arm64"
    assert "sha-" in build["with"]["tags"]
    start = next(step for step in steps if step["name"] == "Start exactly the published digest")
    assert "@${{ steps.image.outputs.digest }}" in start["env"]["PUBLISHED_IMAGE"]
    assert any("tests/system/test_swagger_ui.py" in step.get("run", "") for step in steps)


def test_main_compose_healthcheck_works_without_curl_and_keeps_volume():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api = compose["services"]["petstore"]
    assert api["healthcheck"]["test"][:2] == ["CMD", "python"]
    assert api["volumes"] == [
        "petstore-data:/var/lib/postgresql/data",
        "petstore-media:/var/lib/petstore/media",
    ]
    assert compose["volumes"]["petstore-data"]["name"] == "${PETSTORE_DB_VOLUME:-swagger-petstore-db-data}"
    assert api["environment"]["PETSTORE_SMTP_HOST"] == "${PETSTORE_SMTP_HOST:-}"


def test_local_mail_overlay_is_opt_in_loopback_only_and_has_no_relay():
    compose = yaml.safe_load((ROOT / "docker/compose.mail.yml").read_text())
    assert compose["services"]["petstore"]["environment"]["PETSTORE_SMTP_HOST"] == "mail"
    mail = compose["services"]["mail"]
    assert all(port.startswith("127.0.0.1:") for port in mail["ports"])
    assert mail["environment"]["RelayOptions__SmtpServer"] == ""
    assert mail["environment"]["RelayOptions__AutomaticRelayExpression"] == ""


def test_build_context_excludes_secrets_and_local_database_backups():
    patterns = (ROOT / ".dockerignore").read_text().splitlines()
    assert ".env" in patterns
    assert ".env.*" in patterns
    assert "backups" in patterns


def test_repository_has_no_java_sources_or_maven_build():
    assert not list((ROOT / "src").rglob("*.java"))
    assert not (ROOT / "pom.xml").exists()
    assert not (ROOT / "Dockerfile.java").exists()
    assert not list((ROOT / ".github/workflows").glob("maven*.yml"))
    workflow = yaml.safe_load((ROOT / ".github/workflows/codeql-analysis.yml").read_text())
    initialize = next(step for step in workflow["jobs"]["python"]["steps"] if step.get("with"))
    assert initialize["with"]["languages"] == "python"


def test_original_migration_filenames_are_retained():
    migrations = sorted((ROOT / "resources/db/migration").glob("V*__*.sql"))
    assert {path.name.split("__")[0] for path in migrations} == {f"V{i}" for i in range(1, 12)}


def test_source_resources_and_docker_paths_agree():
    assert Settings().resources == ROOT / "resources"
    assert Settings().static == ROOT / "resources/web"
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "COPY src /app/src" in dockerfile
    assert "PETSTORE_RESOURCE_ROOT=/app/resources" in dockerfile
    assert "PETSTORE_STATIC_ROOT=/app/resources/web" in dockerfile
    assert "filesystem:/app/resources/db/migration" in (ROOT / "docker/entrypoint.sh").read_text()
    compose = yaml.safe_load((ROOT / "tests/docker-compose.yml").read_text())
    build = compose["services"]["api"]["build"]
    assert (ROOT / "tests" / build["context"]).resolve() == ROOT
    assert build["dockerfile"] == "Dockerfile"
    assert not (ROOT / "docker-compose.python.yml").exists()
    assert not (ROOT / "Dockerfile.python.dockerignore").exists()
    assert not (ROOT / "DEPLOY_NOTES.md").exists()
    assert (ROOT / "docs/history.md").exists()
