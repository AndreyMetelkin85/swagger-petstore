from pathlib import Path

import yaml

from petstore.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_dockerfile_builds_the_python_application():
    release = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert not (ROOT / "Dockerfile.python").exists()
    assert "python -m pip install --no-cache-dir --no-deps ." in release
    assert release.index("--requirement requirements-runtime.txt") < release.index("COPY src /app/src")
    assert "petstore-entrypoint" in release
    assert "tomcat" not in release.lower()


def test_publication_requires_python_tests_and_both_platform_scans():
    workflow = yaml.safe_load((ROOT / ".github/workflows/docker-security.yml").read_text())
    matrix = workflow["jobs"]["build"]["strategy"]["matrix"]["include"]
    assert {entry["arch"] for entry in matrix} == {"amd64", "arm64"}
    assert next(entry for entry in matrix if entry["arch"] == "arm64")["runner"] == "ubuntu-24.04-arm"
    assert set(workflow["jobs"]["publish"]["needs"]) == {
        "changes",
        "quality",
        "build",
        "python-verification",
        "runtime",
    }
    steps = workflow["jobs"]["publish"]["steps"]
    assert not any(step.get("uses", "").startswith("docker/build-push-action") for step in steps)
    assert any("imagetools create" in step.get("run", "") and ":latest" in step["run"] for step in steps)
    build = next(step for step in workflow["jobs"]["build"]["steps"] if step.get("id") == "image")
    assert build["with"]["file"] == "Dockerfile"
    assert build["with"]["platforms"] == "linux/${{ matrix.arch }}"
    assert "candidate-" in build["with"]["tags"] and ":latest" not in build["with"]["tags"]
    assert "cache-from" in build["with"] and build["with"]["provenance"] == "mode=max"
    assert "needs.runtime.result == 'success'" in workflow["jobs"]["publish"]["if"]


def test_main_compose_healthcheck_works_without_curl_and_keeps_volume():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api = compose["services"]["petstore"]
    assert api["healthcheck"]["test"][:2] == ["CMD", "python"]
    assert api["volumes"] == [
        "petstore-data:/var/lib/postgresql/data",
        "petstore-media:/var/lib/petstore/media",
        "mail-data:/smtp4dev",
    ]
    assert compose["volumes"]["petstore-data"]["name"] == "${PETSTORE_DB_VOLUME:-swagger-petstore-db-data}"
    assert api["environment"]["PETSTORE_SMTP_HOST"] == "127.0.0.1"
    assert set(compose["services"]) == {"petstore"}
    assert compose["volumes"]["mail-data"]["name"] == "${PETSTORE_MAIL_VOLUME:-swagger-petstore-mail-data}"


def test_embedded_mail_is_loopback_only_and_has_no_external_relay():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    app = compose["services"]["petstore"]
    assert app["environment"]["PETSTORE_EMBEDDED_MAIL"] == "true"
    assert all(port.startswith("127.0.0.1:") for port in app["ports"])
    entrypoint = (ROOT / "docker/entrypoint.sh").read_text()
    assert "RelayOptions__SmtpServer=''" in entrypoint
    assert "RelayOptions__AutomaticRelayExpression=''" in entrypoint
    assert "petstore-run-mail.py" in entrypoint


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
    assert {path.name.split("__")[0] for path in migrations} == {f"V{i}" for i in range(1, 13)}


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
