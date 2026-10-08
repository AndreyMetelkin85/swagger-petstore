"""Бизнес-правила и согласование операций приложения."""

import secrets
import time
from typing import Any

import jwt

from petstore.service.exceptions import AccountException


class TokenService:
    """Выдача и проверка JWT с общим ключом экземпляра приложения."""

    DEFAULT_TTL_SECONDS = 3600

    def __init__(self, secret: str | None = None) -> None:
        """Выбирает настроенный ключ JWT либо временный случайный ключ этого процесса.

        :param secret: Секрет подписи JWT; не выводится в логи.
        :return: Ничего не возвращает.
        """
        if secret is not None and (
            not secret.strip()
            or len(secret.encode("utf-8")) < 32
            or secret == "local-petstore-secret-change-me"
        ):
            raise ValueError("JWT secret must contain at least 32 UTF-8 bytes and must not be the legacy key")
        self.secret = secret.encode("utf-8") if secret is not None else secrets.token_bytes(32)

    def issue_token(self, user: dict[str, Any], ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
        """Выдаёт токен с совместимыми claims sub, role, ver, iat и exp.

        :param user: Строка пользователя, полученная из базы данных.
        :param ttl_seconds: Время жизни JWT в секундах.
        :return: Строковый результат описанной операции.
        """
        now = int(time.time())
        return jwt.encode(  # pyright: ignore[reportUnknownMemberType]
            {
                "sub": user["username"],
                "role": user["role"],
                "ver": user["token_version"],
                "iat": now,
                "exp": now + ttl_seconds,
            },
            self.secret,
            algorithm="HS256",
        )

    def validate(self, token: str) -> dict[str, Any]:
        """Проверяет подпись, типы claims и срок действия, запрещая другие алгоритмы.

        :param token: Строка Bearer-токена для проверки.
        :return: Результат операции типа dict[str, Any].
        """
        try:
            claims: dict[str, Any] = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
                token,
                self.secret,
                algorithms=["HS256"],
                options={"verify_exp": False, "verify_iat": False, "require": ["sub", "role", "ver", "exp"]},
            )
            if (
                claims["role"] not in {"USER", "ADMIN"}
                or not isinstance(claims["sub"], str)
                or type(claims["ver"]) is not int
                or type(claims["exp"]) is not int
            ):
                raise ValueError("Invalid claim types")
            if claims["exp"] <= int(time.time()):
                raise AccountException(401, "TOKEN_EXPIRED", "Access token has expired")
            return claims
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as exc:
            raise AccountException(401, "INVALID_TOKEN", "Access token is invalid") from exc
