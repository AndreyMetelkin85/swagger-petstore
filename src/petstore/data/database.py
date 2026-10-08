"""Хранение данных PostgreSQL и транзакционные SQL-операции."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from petstore.config import Settings

Row = dict[str, Any]
DbConnection = psycopg.Connection[Row]


class Database:
    """Общий пул PostgreSQL с явными транзакциями и безопасным завершением."""

    def __init__(self, settings: Settings) -> None:
        """Настраивает пул без подключения к базе и без изменения пользовательских данных.

        :param settings: Настройки приложения и его инфраструктурных подключений.
        :return: Ничего не возвращает.
        """
        self.pool: ConnectionPool[DbConnection] = ConnectionPool(
            settings.db_url,
            kwargs={
                "user": settings.db_user,
                "password": settings.db_password,
                "row_factory": dict_row,
                "connect_timeout": 5,
            },
            min_size=1,
            max_size=10,
            timeout=10,
            open=False,
        )

    def start(self) -> None:
        """Открывает пул соединений после успешного применения миграций Flyway.

        :return: Ничего не возвращает.
        """
        self.pool.open(wait=True, timeout=15)

    def close(self) -> None:
        """Закрывает соединения и потоки пула при остановке приложения.

        :return: Ничего не возвращает.
        """
        self.pool.close()

    @contextmanager
    def connect(self) -> Generator[DbConnection, None, None]:
        """Предоставляет соединение; фиксирует успешную транзакцию и откатывает её при исключении.

        При нормальном завершении блока соединение фиксирует транзакцию. Исключение вызывает
        rollback; соединение возвращается в пул. Вызывающий код работает внутри with.

        :yield: Значение текущего шага управляемого контекстом жизненного цикла.
        """
        with self.pool.connection() as connection:
            yield connection

    def is_healthy(self) -> bool:
        """Проверяет доступность PostgreSQL, не раскрывая детали соединения.

        :return: True при выполнении проверяемого условия, иначе False.
        """
        try:
            with self.connect() as connection:
                return connection.execute("SELECT 1 AS healthy").fetchone() == {"healthy": 1}
        except (psycopg.Error, RuntimeError):
            return False
