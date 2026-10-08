"""Инфраструктурные проверки сборки, миграций и публикации."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen


def classify(paths: list[str]) -> dict[str, bool]:
    """Выбирает полные проверки для неизвестных файлов и изменений CI.

    :param paths: Пути изменённых файлов относительно корня репозитория.
    :return: Результат описанной проверки или запроса.
    """
    backend = runtime = False
    for path in paths:
        if path.startswith("docs/") or path.endswith(".md") or path == ".gitignore":
            continue
        backend = runtime = True
    return {"backend": backend, "runtime": runtime, "build": runtime or backend}


def previous_release() -> str | None:
    """Находит последний master с успешно выполненной публикацией.

    :return: Результат описанной проверки или запроса.
    """
    repository = os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("GITHUB_TOKEN")
    if not repository or not token:
        return None
    api = os.getenv("GITHUB_API_URL", "https://api.github.com")

    def get(path: str):
        """Читает JSON GitHub API с авторизацией и ограничением времени запроса.

        :param path: Путь ресурса или файла, сформированный вызывающим кодом.
        :return: Результат описанной проверки или запроса.
        """
        request = Request(
            api + path, headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}
        )
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    try:
        runs = get(
            f"/repos/{repository}/actions/workflows/docker-security.yml/runs?branch=master&event=push&status=success&per_page=30"
        )
        for run in runs["workflow_runs"]:
            if run["head_sha"] == os.getenv("GITHUB_SHA"):
                continue
            jobs = get(f"/repos/{repository}/actions/runs/{run['id']}/jobs?per_page=100")
            if any(job["name"] == "publish" and job["conclusion"] == "success" for job in jobs["jobs"]):
                return run["head_sha"]
    except Exception:
        print("Release baseline unavailable; selecting full verification")
    return None


def main() -> None:
    """Выбирает проверки по изменённым файлам относительно проверенного релиза.

    :return: Ничего не возвращает.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    arguments = parser.parse_args()
    base = arguments.base or previous_release()
    result = {"backend": True, "runtime": True, "build": True}
    if base:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "-z", base, "HEAD"], capture_output=True, check=False
        )
        if diff.returncode == 0:
            result = classify([name for name in diff.stdout.decode("utf-8").split("\0") if name])
    if os.getenv("GITHUB_EVENT_NAME") in {"schedule", "workflow_dispatch"}:
        result = {key: True for key in result}
    output = "".join(f"{key}={str(value).lower()}\n" for key, value in result.items())
    if os.getenv("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as target:
            target.write(output)
    print(json.dumps({"baseline": base, **result}))


if __name__ == "__main__":
    main()
