"""Prepare separate Flyway-migrated databases for parallel test workers."""

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor


def prepare(container: str, name: str) -> None:
    """Names originate only from this module; no destructive reset or user database."""
    subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "petstore",
            "-d",
            "petstore",
            "-c",
            f"CREATE DATABASE {name}",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "docker",
            "exec",
            "-e",
            f"FLYWAY_URL=jdbc:postgresql://127.0.0.1:5432/{name}",
            "-e",
            "FLYWAY_USER=petstore",
            "-e",
            "FLYWAY_PASSWORD=petstore",
            container,
            "/opt/flyway/flyway",
            "-locations=filesystem:/app/resources/db/migration",
            "migrate",
        ],
        check=True,
        capture_output=True,
    )
    print("Prepared isolated database: " + name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--container", choices=["petstore-python-preview", "petstore-ci-regression"], required=True
    )
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    arguments = parser.parse_args()
    with ThreadPoolExecutor(max_workers=arguments.workers) as workers:
        list(
            workers.map(
                lambda index: prepare(arguments.container, f"petstore_python_test_gw{index}"),
                range(arguments.workers),
            )
        )


if __name__ == "__main__":
    main()
