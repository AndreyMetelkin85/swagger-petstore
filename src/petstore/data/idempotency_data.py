"""Хранение данных PostgreSQL и транзакционные SQL-операции."""

import hashlib
import json
from uuid import UUID

from psycopg.types.json import Jsonb

from petstore.data.database import DbConnection, Row
from petstore.data.payment_data import PaymentData
from petstore.service.exceptions import ApiException
from petstore.utils.responses import Responses


class IdempotencyData:
    """Сохранённые повторы команд с транзакционными advisory-блокировками."""

    @staticmethod
    def digest(payload: Row) -> str:
        """Вычисляет хеш канонической безопасной команды без сохранения исходного запроса.

        :param payload: Тело команды либо ограниченное содержимое загруженного файла.
        :return: Строковый результат описанной операции.
        """
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def replay(
        connection: DbConnection, actor: UUID, operation: str, key: UUID | None, payload: Row
    ) -> tuple[Row, int] | None:
        """Блокирует ключ и возвращает результат только при совпадении пользователя, операции и хеша.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :param operation: Имя операции для проверки области ключа идемпотентности.
        :param key: Ключ повторного запроса либо идентификатор операции.
        :param payload: Тело команды либо ограниченное содержимое загруженного файла.
        :return: Результат операции типа tuple[Row, int] | None.
        """
        if key is None:
            return None
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (PaymentData.advisory_key(key),))
        row = connection.execute(
            "SELECT * FROM api_idempotency WHERE user_id=%s AND operation=%s AND key=%s",
            (actor, operation, key),
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != IdempotencyData.digest(payload):
            raise ApiException(
                409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was used with a different request"
            )
        return row["result"], row["status_code"]

    @staticmethod
    def save(
        connection: DbConnection,
        actor: UUID,
        operation: str,
        key: UUID | None,
        payload: Row,
        result: Row,
        status: int,
    ) -> None:
        """Сохраняет безопасный JSON-результат в той же транзакции, что и изменение.

        :param connection: Открытое соединение текущей транзакции; повторная транзакция не создаётся.
        :param actor: Авторизованный пользователь, выполняющий операцию.
        :param operation: Имя операции для проверки области ключа идемпотентности.
        :param key: Ключ повторного запроса либо идентификатор операции.
        :param payload: Тело команды либо ограниченное содержимое загруженного файла.
        :param result: Ответ контроллера с уже сформированным JSON и HTTP-статусом.
        :param status: Статус ресурса либо HTTP-ответа согласно операции.
        :return: Ничего не возвращает.
        """
        if key is not None:
            plain = json.loads(bytes(Responses(result).body))
            connection.execute(
                "INSERT INTO api_idempotency (user_id,operation,key,request_hash,result,status_code) VALUES (%s,%s,%s,%s,%s,%s)",
                (actor, operation, key, IdempotencyData.digest(payload), Jsonb(plain), status),
            )
