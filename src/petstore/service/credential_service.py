"""Бизнес-правила и согласование операций приложения."""

import hashlib
import hmac
import secrets

import bcrypt


class CredentialService:
    """Хеширование паролей и генерация одноразовых кодов без раскрытия значений."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Создаёт bcrypt-хеш со стоимостью 10, совместимый с существующими аккаунтами.

        :param password: Пароль для проверки или хеширования; не сохраняется в логах.
        :return: Строковый результат описанной операции.
        """
        return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=10, prefix=b"2a")).decode(
            "ascii"
        )

    @staticmethod
    def is_bcrypt(value: str) -> bool:
        """Определяет поддерживаемый вариант сохранённого bcrypt-хеша.

        :param value: Значение, проверяемое или преобразуемое текущей операцией.
        :return: True при выполнении проверяемого условия, иначе False.
        """
        return value.startswith(("$2a$", "$2b$", "$2y$"))

    @classmethod
    def password_matches(cls, password: str, stored: str) -> bool:
        """Проверяет хеш либо прежний открытый пароль без обычного сравнения секретов.

        :param password: Пароль для проверки или хеширования; не сохраняется в логах.
        :param stored: Сохранённое значение для сравнения.
        :return: True при выполнении проверяемого условия, иначе False.
        """
        if cls.is_bcrypt(stored):
            try:
                # jBCrypt обрезал прежние пароли входа до ограничения bcrypt в байтах.
                return bcrypt.checkpw(password.encode("utf-8")[:72], stored.encode("ascii"))
            except (ValueError, UnicodeError):
                return False
        return hmac.compare_digest(password.encode("utf-8"), stored.encode("utf-8"))

    @staticmethod
    def new_one_time_code() -> str:
        """Создаёт URL-безопасный код из 32 случайных байтов без padding.

        :return: Строковый результат описанной операции.
        """
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_one_time_code(code: str) -> str:
        """Возвращает SHA-256 одноразового кода в нижнем шестнадцатеричном регистре.

        :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
        :return: Строковый результат описанной операции.
        """
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    @classmethod
    def code_matches(cls, code: str, stored: str | None) -> bool:
        """Сравнивает переданный одноразовый код с сохранённым хешем.

        :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
        :param stored: Сохранённое значение для сравнения.
        :return: True при выполнении проверяемого условия, иначе False.
        """
        return stored is not None and hmac.compare_digest(cls.hash_one_time_code(code), stored)
