import re
from pathlib import Path

import pytest
import yaml

from petstore.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_dockerfile_builds_the_python_application():
    release = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert not (ROOT / "Dockerfile.python").exists()
    assert "python -m pip install --no-cache-dir --no-deps ." in release
    assert release.index("--requirement requirements-runtime.txt") < release.index(
        "COPY --chown=petstore:petstore src /app/src"
    )
    assert "petstore-entrypoint" in release
    assert "tomcat" not in release.lower()


def test_publication_requires_python_tests_and_both_platform_scans():
    workflow = yaml.safe_load((ROOT / ".github/workflows/docker-security.yml").read_text())
    jobs = workflow["jobs"]
    for arch, runner in (("amd64", "ubuntu-24.04"), ("arm64", "ubuntu-24.04-arm")):
        assert jobs["build-" + arch]["with"] == {"arch": arch, "runner": runner}
        assert jobs["verify-" + arch]["needs"] == "build-" + arch
    for lane in ("python-verification", "swagger", "runtime"):
        assert jobs[lane]["needs"] == ["changes", "build-amd64"]
        assert "build-amd64.outputs.candidate_digest" in jobs[lane]["with"]["digest"]
    assert set(jobs["publish"]["needs"]) == {
        "changes",
        "quality",
        "build-amd64",
        "build-arm64",
        "verify-amd64",
        "verify-arm64",
        "python-verification",
        "swagger",
        "runtime",
    }
    steps = jobs["publish"]["steps"]
    assert not any(step.get("uses", "").startswith("docker/build-push-action") for step in steps)
    assert any("imagetools create" in step.get("run", "") and ":latest" in step["run"] for step in steps)
    assert any("MAIL_AMD64" in step.get("run", "") and "MAIL_ARM64" in step["run"] for step in steps)
    platform = yaml.safe_load((ROOT / ".github/workflows/build-platform.yml").read_text())
    build = next(step for step in platform["jobs"]["build"]["steps"] if step.get("id") == "image")
    assert build["with"]["file"] == "Dockerfile"
    assert build["with"]["platforms"] == "linux/${{ inputs.arch }}"
    assert "candidate-" in build["with"]["tags"] and ":latest" not in build["with"]["tags"]
    assert "type=registry" in build["with"]["cache-to"] and "mode=max" in build["with"]["cache-to"]
    assert build["with"]["sbom"] and build["with"]["provenance"] == "mode=max"


def publication_allowed(results, backend=True, event="push", ref="refs/heads/master"):
    """Проверяет действующее условие публикации на выбранных состояниях jobs.

    :param results: Состояния jobs GitHub Actions.
    :param backend: Изменялся ли исполняемый бэкенд.
    :param event: Тип события GitHub Actions.
    :param ref: Ссылка проверяемой ветки Git.
    :return: Результат описанной проверки или подготовки тестовых данных.
    """
    workflow = yaml.safe_load((ROOT / ".github/workflows/docker-security.yml").read_text())
    expression = workflow["jobs"]["publish"]["if"]
    expression = expression.replace("always()", "True").replace("&&", " and ").replace("||", " or ")
    values = {
        "github.event_name": event,
        "github.ref": ref,
        "needs.changes.outputs.runtime": "true",
        "needs.changes.outputs.backend": str(backend).lower(),
    }
    values.update({"needs." + name + ".result": result for name, result in results.items()})
    expression = re.sub(
        r"(?:needs|github)\.[a-zA-Z0-9_.-]+", lambda match: repr(values[match.group()]), expression
    )
    return eval(expression, {"__builtins__": {}}, {})


@pytest.mark.parametrize(
    "job",
    [
        "changes",
        "quality",
        "build-amd64",
        "build-arm64",
        "verify-amd64",
        "verify-arm64",
        "python-verification",
        "swagger",
        "runtime",
    ],
)
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_each_required_gate_prevents_any_promotion(job, result):
    results = dict.fromkeys(
        [
            "changes",
            "quality",
            "build-amd64",
            "build-arm64",
            "verify-amd64",
            "verify-arm64",
            "python-verification",
            "swagger",
            "runtime",
        ],
        "success",
    )
    assert publication_allowed(results)
    assert not publication_allowed(results | {job: result})


def test_ui_release_requires_expected_skips_and_never_publishes_pr_or_dev():
    results = dict.fromkeys(
        [
            "changes",
            "quality",
            "build-amd64",
            "build-arm64",
            "verify-amd64",
            "verify-arm64",
            "python-verification",
            "swagger",
            "runtime",
        ],
        "success",
    )
    fast = results | {"python-verification": "skipped", "swagger": "skipped"}
    assert publication_allowed(fast, backend=False)
    assert not publication_allowed(fast, backend=True)
    assert not publication_allowed(fast | {"swagger": "failure"}, backend=False)
    assert not publication_allowed(results, event="pull_request")
    assert not publication_allowed(results, ref="refs/heads/dev")


def test_main_compose_healthcheck_works_without_curl_and_keeps_volume():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api = compose["services"]["backend"]
    assert "petstore-api-health.py" in (ROOT / "Dockerfile").read_text()
    assert api["volumes"] == ["petstore-media:/var/lib/petstore/media"]
    assert compose["services"]["postgres"]["volumes"] == ["petstore-data:/var/lib/postgresql/data"]
    assert compose["services"]["mail"]["volumes"] == ["mail-data:/smtp4dev"]
    assert compose["volumes"]["petstore-data"]["name"] == "${PETSTORE_DB_VOLUME:-swagger-petstore-db-data}"
    assert api["environment"]["PETSTORE_SMTP_HOST"] == "mail"
    assert set(compose["services"]) == {"backend", "frontend", "postgres", "mail", "migrations"}
    assert compose["volumes"]["mail-data"]["name"] == "${PETSTORE_MAIL_VOLUME:-swagger-petstore-mail-data}"


def test_separate_mail_is_loopback_only_and_has_no_external_relay():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    app = compose["services"]["mail"]
    assert all(port.startswith("127.0.0.1:") for port in app["ports"])
    assert app["environment"]["RelayOptions__SmtpServer"] == ""
    assert app["environment"]["RelayOptions__AutomaticRelayExpression"] == ""
    assert "Serilog" in str(app["environment"])
    assert "run_mail.py" in (ROOT / "docker/Dockerfile.mail").read_text()


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
    assert "COPY --chown=petstore:petstore src /app/src" in dockerfile
    assert "PETSTORE_RESOURCE_ROOT=/app/resources" in dockerfile
    assert "PETSTORE_STATIC_ROOT=/app/resources/web" in dockerfile
    assert "filesystem:/app/resources/db/migration" in (ROOT / "docker-compose.yml").read_text()
    compose = yaml.safe_load((ROOT / "tests/docker-compose.yml").read_text())
    build = compose["services"]["api"]["build"]
    assert (ROOT / "tests" / build["context"]).resolve() == ROOT
    assert build["dockerfile"] == "Dockerfile"
    assert not (ROOT / "docker-compose.python.yml").exists()
    assert not (ROOT / "Dockerfile.python.dockerignore").exists()
    assert not (ROOT / "DEPLOY_NOTES.md").exists()
    assert (ROOT / "docs/history.md").exists()
