"""Report the critical path and BuildKit export time from the current Actions run."""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen


def elapsed(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    return max(0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())


def cache_export_seconds(log: str) -> float | None:
    step = None
    for line in log.splitlines():
        start = re.search(r"#(\d+) exporting cache to registry", line)
        if start:
            step = start.group(1)
        if step:
            done = re.search(r"#" + step + r" DONE ([0-9.]+)s", line)
            if done:
                return float(done.group(1))
    return None


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    api = os.getenv("GITHUB_API_URL", "https://api.github.com")

    def get(path: str) -> bytes:
        request = Request(
            api + path,
            headers={
                "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                "Accept": "application/vnd.github+json",
            },
        )
        with urlopen(request, timeout=20) as response:
            return response.read()

    try:
        run = json.loads(get(f"/repos/{repository}/actions/runs/{run_id}"))
        jobs = json.loads(get(f"/repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"))["jobs"]
    except Exception:
        print("CI timings unavailable from GitHub API; test and release results are unchanged.")
        return
    completed = [job for job in jobs if job["completed_at"] and job["name"] != "timing"]
    critical_end = max((job["completed_at"] for job in completed), default=run["created_at"])
    report = [
        "## Delivery timing",
        f"Run to completed gates/promotion: {elapsed(run['created_at'], critical_end):.0f}s (timing job excluded).",
        "Parallel jobs are not added together. Queue time is reported per job.",
        "",
        "| Job | Result | Queue, s | Execution, s | Registry cache export, s |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for job in completed:
        cache = None
        if job["name"].startswith("build-") and job["conclusion"] == "success":
            try:
                cache = cache_export_seconds(
                    subprocess.run(
                        ["gh", "api", f"/repos/{repository}/actions/jobs/{job['id']}/logs"],
                        capture_output=True,
                        check=True,
                        timeout=30,
                    ).stdout.decode()
                )
            except Exception:
                pass
        queue = elapsed(job["created_at"], job["started_at"])
        duration = elapsed(job["started_at"], job["completed_at"])
        report.append(
            f"| {job['name']} | {job['conclusion']} | {queue if queue is not None else '-'} | "
            f"{duration if duration is not None else '-'} | {cache if cache is not None else '-'} |"
        )
    report += ["", "| Job / stage | Seconds |", "| --- | ---: |"]
    for job in completed:
        for step in job["steps"]:
            if step["conclusion"] == "success" and re.search(
                r"Build each|Load |Contracts and|Scan |Unit and integration|System contracts|Every Swagger|Actual frontend|Promote",
                step["name"],
            ):
                report.append(
                    f"| {job['name']} / {step['name']} | {elapsed(step['started_at'], step['completed_at'])} |"
                )
    output = "\n".join(report) + "\n"
    print(output)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as target:
            target.write(output)


if __name__ == "__main__":
    main()
