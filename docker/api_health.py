"""Проверка готовности API и его соединения с PostgreSQL."""

from urllib.request import urlopen


def main() -> None:
    """Проверяет /health; ошибка HTTP или соединения завершает проверку неуспешно.

    :return: Ничего не возвращает.
    """
    with urlopen("http://127.0.0.1:8080/api/v3/health", timeout=3) as response:
        if response.status != 200:
            raise OSError("API не готов принимать запросы")


if __name__ == "__main__":
    main()
