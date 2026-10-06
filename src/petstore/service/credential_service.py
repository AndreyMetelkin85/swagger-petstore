"""Compatible bcrypt passwords and SHA-256 one-time-code hashes."""

import hashlib
import hmac
import secrets

import bcrypt


class CredentialService:
    """Password hashing and one-time code generation without exposing raw values."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Create a bcrypt hash at the original cost of ten.

        :param password: Password; new inputs are validated, legacy logins retain jBCrypt truncation.
        """
        return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=10, prefix=b"2a")).decode(
            "ascii"
        )

    @staticmethod
    def is_bcrypt(value: str) -> bool:
        """Recognize the existing bcrypt variants.

        :param value: Persisted password representation.
        """
        return value.startswith(("$2a$", "$2b$", "$2y$"))

    @classmethod
    def password_matches(cls, password: str, stored: str) -> bool:
        """Verify existing hashes or legacy plaintext without timing-sensitive equality.

        :param password: Submitted password.
        :param stored: Existing database value.
        """
        if cls.is_bcrypt(stored):
            try:
                # jBCrypt truncates legacy login inputs to the bcrypt byte limit.
                return bcrypt.checkpw(password.encode("utf-8")[:72], stored.encode("ascii"))
            except (ValueError, UnicodeError):
                return False
        return hmac.compare_digest(password.encode("utf-8"), stored.encode("utf-8"))

    @staticmethod
    def new_one_time_code() -> str:
        """Generate the same 32-byte, URL-safe code format without padding."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_one_time_code(code: str) -> str:
        """Hash a code using the original lowercase SHA-256 hex representation.

        :param code: Raw one-time code.
        """
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    @classmethod
    def code_matches(cls, code: str, stored: str | None) -> bool:
        """Compare a supplied code to its persisted hash.

        :param code: Supplied one-time code.
        :param stored: Persisted hash, if any.
        """
        return stored is not None and hmac.compare_digest(cls.hash_one_time_code(code), stored)
