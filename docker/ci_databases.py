"""Создание отдельных баз с миграциями Flyway для параллельных тестов."""

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor


def prepare(container: str, name: str) -> None:
    """Создаёт изолированную базу и применяет миграции из образа API.

    :param container: Разрешённый контейнер API с CLI Flyway.
    :param name: Имя тестовой базы, сформированное этим модулем.
    :return: None после успешного создания базы и применения миграций.
    """
    subprocess.run(
        [
            "docker",
            "exec",
            "petstore-python-db",
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
            f"FLYWAY_URL=jdbc:postgresql://postgres:5432/{name}",
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
    """Создаёт базовую тестовую базу и отдельные базы для worker-процессов.

    :return: None после завершения подготовки всех баз.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--container", choices=["petstore-python-preview", "petstore-ci-regression"], required=True
    )
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    arguments = parser.parse_args()
    prepare(arguments.container, "petstore_python_test")
    with ThreadPoolExecutor(max_workers=arguments.workers) as workers:
        list(
            workers.map(
                lambda index: prepare(arguments.container, f"petstore_python_test_gw{index}"),
                range(arguments.workers),
            )
        )


if __name__ == "__main__":
    main()
