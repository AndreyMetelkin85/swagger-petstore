import ast
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_backend_does_not_contain_frontend_sources_or_node_build():
    assert not (ROOT / "ui").exists()
    assert not (ROOT / "package.json").exists()
    assert not (ROOT / "docker/sync_frontend.py").exists()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "frontend-build" not in dockerfile
    assert "npm" not in dockerfile
    assert "nginx-light" not in dockerfile
    assert "FROM postgres:" not in dockerfile
    assert "smtp4dev" not in dockerfile
    workflows = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / ".github/workflows").glob("*.yml"))
    assert "setup-node" not in workflows
    assert "working-directory: ui" not in workflows


def test_shared_compose_separates_processes_and_preserves_data_volumes():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert set(services) == {"frontend", "backend", "postgres", "migrations", "mail"}
    assert all("build" not in service for service in services.values())
    assert services["migrations"]["image"] == services["backend"]["image"]
    assert services["migrations"]["entrypoint"] == ["/opt/flyway/flyway"]
    assert services["backend"]["depends_on"]["migrations"]["condition"] == "service_completed_successfully"
    assert services["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"
    assert services["backend"]["volumes"] == ["petstore-media:/var/lib/petstore/media"]
    assert services["postgres"]["volumes"] == ["petstore-data:/var/lib/postgresql/data"]
    assert services["mail"]["volumes"] == ["mail-data:/smtp4dev"]
    assert all(
        port.startswith("127.0.0.1:") for service in services.values() for port in service.get("ports", [])
    )


def test_every_backend_function_has_russian_parameter_and_result_documentation():
    errors = []
    for folder in ("src", "docker"):
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                doc = ast.get_docstring(node) or ""
                key = f"{path.relative_to(ROOT)}:{node.name}"
                if not re.search("[а-яА-Я]", doc):
                    errors.append(key + ": нет русского описания")
                args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                names = [a.arg for a in args if a.arg not in {"self", "cls"}]
                names += [a.arg for a in (node.args.vararg, node.args.kwarg) if a]
                for name in names:
                    if f":param {name}:" not in doc:
                        errors.append(key + f": не описан {name}")
                if ":return:" not in doc and ":yield:" not in doc:
                    errors.append(key + ": не описан результат")
    assert not errors, "\n".join(errors)
