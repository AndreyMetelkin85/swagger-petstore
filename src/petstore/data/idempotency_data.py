"""Persistent replay for cart replacement, draft creation and placement."""

import hashlib
import json
from uuid import UUID

from psycopg.types.json import Jsonb

from petstore.data.database import DbConnection, Row
from petstore.data.payment_data import PaymentData
from petstore.service.exceptions import ApiException
from petstore.utils.responses import Responses


class IdempotencyData:
    """Share transaction-scoped advisory locks with the existing payment protocol."""

    @staticmethod
    def digest(payload: Row) -> str:
        """Hash a canonical nonsensitive command; never persist its raw request."""
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def replay(
        connection: DbConnection, actor: UUID, operation: str, key: UUID | None, payload: Row
    ) -> tuple[Row, int] | None:
        """Lock a key and return its committed result only for the same actor/operation/hash."""
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
        """Persist a safe JSON result in the same transaction as the mutation."""
        if key is not None:
            plain = json.loads(bytes(Responses(result).body))
            connection.execute(
                "INSERT INTO api_idempotency (user_id,operation,key,request_hash,result,status_code) VALUES (%s,%s,%s,%s,%s,%s)",
                (actor, operation, key, IdempotencyData.digest(payload), Jsonb(plain), status),
            )
