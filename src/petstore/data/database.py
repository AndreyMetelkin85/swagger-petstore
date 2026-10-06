"""Bounded psycopg pool; Flyway SQL migrations run separately before startup."""

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
    """Connection factory with explicit transaction boundaries and safe shutdown."""

    def __init__(self, settings: Settings) -> None:
        """Configure the pool without connecting or migrating user data.

        :param settings: Compatible PostgreSQL connection settings.
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
        """Open connections after Flyway has validated and migrated the database."""
        self.pool.open(wait=True, timeout=15)

    def close(self) -> None:
        """Close pool threads and connections during application shutdown."""
        self.pool.close()

    @contextmanager
    def connect(self) -> Generator[DbConnection, None, None]:
        """Commit successful operations and roll back exceptions before returning the connection."""
        with self.pool.connection() as connection:
            yield connection

    def is_healthy(self) -> bool:
        """Check PostgreSQL availability without disclosing connection failures."""
        try:
            with self.connect() as connection:
                return connection.execute("SELECT 1 AS healthy").fetchone() == {"healthy": 1}
        except (psycopg.Error, RuntimeError):
            return False
