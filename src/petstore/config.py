"""Read the same PETSTORE_* environment variables as the existing container."""

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def environment(name: str, fallback: str) -> str:
    """Use the fallback for missing or whitespace-only environment variables.

    :param name: Environment variable name.
    :param fallback: Default value from the existing application.
    """
    value = os.getenv(name)
    return value if value is not None and value.strip() else fallback


@dataclass(frozen=True)
class Settings:
    """Runtime configuration without exposing database credentials in repr."""

    db_url: str = field(default="postgresql://localhost:5432/petstore", repr=False)
    db_user: str = "petstore"
    db_password: str = field(default="petstore", repr=False)
    token_secret: str | None = field(default=None, repr=False)
    public_base_url: str = "http://localhost:8080/api/v3"
    expose_test_links: bool = True
    expire_interval: float = 30.0
    test_support: bool = False
    smtp_host: str | None = None
    smtp_port: int = 25
    smtp_timeout: float = 5.0
    smtp_from: str = "noreply@petstore.test"
    mail_frontend_url: str | None = None
    resources: Path = ROOT / "resources"
    static: Path = ROOT / "resources/web"
    media_root: Path = ROOT / ".media"

    @classmethod
    def from_env(cls) -> "Settings":
        """Load compatible environment variables; accept JDBC URLs during transition."""
        secret = os.getenv("PETSTORE_TOKEN_SECRET")
        return cls(
            db_url=environment("PETSTORE_DB_URL", "postgresql://localhost:5432/petstore").removeprefix(
                "jdbc:"
            ),
            db_user=environment("PETSTORE_DB_USER", "petstore"),
            db_password=environment("PETSTORE_DB_PASSWORD", "petstore"),
            token_secret=secret if secret and secret.strip() else None,
            public_base_url=environment("PETSTORE_PUBLIC_BASE_URL", "http://localhost:8080/api/v3")
            .strip()
            .rstrip("/"),
            expose_test_links=os.getenv("PETSTORE_EXPOSE_TEST_LINKS", "true").lower() == "true",
            test_support=os.getenv("PETSTORE_TEST_SUPPORT", "false").lower() == "true",
            smtp_host=os.getenv("PETSTORE_SMTP_HOST") or None,
            smtp_port=int(environment("PETSTORE_SMTP_PORT", "25")),
            smtp_timeout=float(environment("PETSTORE_SMTP_TIMEOUT", "5")),
            smtp_from=environment("PETSTORE_SMTP_FROM", "noreply@petstore.test"),
            mail_frontend_url=(os.getenv("PETSTORE_MAIL_FRONTEND_URL") or "").rstrip("/") or None,
            resources=Path(os.getenv("PETSTORE_RESOURCE_ROOT", str(ROOT / "resources"))),
            static=Path(os.getenv("PETSTORE_STATIC_ROOT", str(ROOT / "resources/web"))),
            media_root=Path(os.getenv("PETSTORE_MEDIA_ROOT", str(ROOT / ".media"))),
        )
