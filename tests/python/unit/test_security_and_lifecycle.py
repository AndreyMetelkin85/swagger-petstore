import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, Mock
from uuid import UUID, uuid4

import jwt
import pytest

from petstore.config import Settings
from petstore.data.payment_data import PaymentData
from petstore.data.user_data import UserData
from petstore.model.enums import OrderStatus
from petstore.service.auth_service import AuthService, LoginAttempts
from petstore.service.credential_service import CredentialService
from petstore.service.exceptions import AccountException
from petstore.service.token_service import TokenService
from petstore.utils.responses import Responses, public_user


@pytest.mark.parametrize("source", list(OrderStatus))
@pytest.mark.parametrize("target", list(OrderStatus))
def test_full_order_transition_matrix(source, target):
    allowed = {
        ("draft", "placed"),
        ("placed", "approved"),
        ("placed", "cancelled"),
        ("approved", "shipped"),
        ("approved", "cancelled"),
        ("shipped", "delivered"),
    }
    assert source.can_transition_to(target) == ((source.value, target.value) in allowed)


@pytest.mark.parametrize("status", list(OrderStatus))
def test_order_active_and_complete_states(status):
    assert status.is_active == (status.value in {"placed", "approved", "shipped"})
    assert status.is_complete == (status.value in {"delivered", "cancelled", "expired"})


@pytest.mark.parametrize("password", ["ValidPass123", "Пароль123", "a" * 72, "a" * 100])
def test_bcrypt_and_legacy_password_compatibility(password):
    service = CredentialService()
    hashed = service.hash_password(password)
    assert hashed.startswith("$2a$10$")
    assert service.password_matches(password, hashed)
    assert not service.password_matches("WrongPass", hashed)
    assert service.password_matches(password, password)
    for prefix in ("$2a$", "$2b$", "$2y$"):
        assert service.password_matches(password, prefix + hashed[4:])


def test_bad_bcrypt_is_false_not_an_internal_error():
    assert not CredentialService.password_matches("ValidPass123", "$2a$invalid")


def test_confirmation_code_format_and_hash():
    code = CredentialService.new_one_time_code()
    assert len(base64.urlsafe_b64decode(code + "=")) == 32
    assert "=" not in code
    assert CredentialService.hash_one_time_code("abc") == hashlib.sha256(b"abc").hexdigest()
    assert CredentialService.code_matches(code, CredentialService.hash_one_time_code(code))
    assert not CredentialService.code_matches(code, None)


@pytest.mark.parametrize("secret", ["", "a" * 31, " " * 40, "local-petstore-secret-change-me"])
def test_insecure_configured_key_is_rejected(secret):
    with pytest.raises(ValueError):
        TokenService(secret)


def test_java_style_jwt_signature_and_claims_are_accepted():
    secret = "test-key-for-compatibility-1234567890"
    now = int(time.time())
    claims = {"sub": "existing-user", "role": "USER", "ver": 2, "iat": now, "exp": now + 300}

    def encode(value):
        return (
            base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=").decode()
        )

    unsigned = encode({"alg": "HS256", "typ": "JWT"}) + "." + encode(claims)
    signature = (
        base64.urlsafe_b64encode(hmac.new(secret.encode(), unsigned.encode(), hashlib.sha256).digest())
        .rstrip(b"=")
        .decode()
    )
    assert TokenService(secret).validate(unsigned + "." + signature) == claims


@pytest.mark.parametrize(
    "mutations,expected",
    [
        ({"exp": 0}, "TOKEN_EXPIRED"),
        ({"role": "ROOT"}, "INVALID_TOKEN"),
        ({"ver": "1"}, "INVALID_TOKEN"),
        ({"exp": "1"}, "INVALID_TOKEN"),
    ],
)
def test_invalid_token_claims(mutations, expected):
    service = TokenService("test-key-for-compatibility-1234567890")
    claims = {"sub": "user", "role": "USER", "ver": 0, "exp": int(time.time()) + 300} | mutations
    with pytest.raises(AccountException) as error:
        service.validate(jwt.encode(claims, service.secret, algorithm="HS256"))
    assert error.value.code == expected


def test_issued_tokens_have_original_fields_and_expiry():
    service = TokenService()
    user = {"username": "user", "role": "USER", "token_version": 3}
    claims = service.validate(service.issue_token(user))
    assert set(claims) == {"sub", "role", "ver", "iat", "exp"}
    assert claims["exp"] - claims["iat"] == 3600


@pytest.mark.parametrize(
    "authorization,code",
    [
        (None, "UNAUTHORIZED"),
        ("", "UNAUTHORIZED"),
        ("Basic invalid", "INVALID_TOKEN"),
        ("Bearer ", "INVALID_TOKEN"),
        ("Bearer invalid", "INVALID_TOKEN"),
    ],
)
def test_authorization_header_validation(authorization, code):
    auth = AuthService(Mock(spec=UserData), Settings())
    with pytest.raises(AccountException) as error:
        auth.authorize(authorization)
    assert error.value.code == code


@pytest.mark.parametrize(
    "mutations,roles,code",
    [
        ({"user_status": "PENDING"}, (), "ACCOUNT_NOT_VERIFIED"),
        ({"user_status": "BLOCKED"}, (), "ACCOUNT_BLOCKED"),
        ({"token_version": 1}, (), "INVALID_TOKEN"),
        ({"role": "ADMIN"}, (), "INVALID_TOKEN"),
        ({}, ("ADMIN",), "FORBIDDEN"),
    ],
)
def test_authorization_checks_current_database_state(mutations, roles, code):
    user = {"id": uuid4(), "username": "user", "role": "USER", "user_status": "ACTIVE", "token_version": 0}
    repository = Mock(spec=UserData)
    auth = AuthService(repository, Settings())
    token = auth.token_service.issue_token(user)
    repository.find_user_by_name.return_value = user | mutations
    with pytest.raises(AccountException) as error:
        auth.authorize("Bearer " + token, *roles)
    assert error.value.code == code


def test_login_locks_on_fifth_failure():
    repository = Mock(spec=UserData)
    repository.find_user_by_email.return_value = None
    auth = AuthService(repository, Settings())
    for expected in (401, 401, 401, 401, 429, 429):
        with pytest.raises(AccountException) as error:
            auth.authenticated_user("missing@example.com", "WrongPass")
        assert error.value.status == expected


@pytest.mark.parametrize(
    "expired,stored,expected",
    [
        (False, None, "INVALID_CONFIRMATION_LINK"),
        (True, "valid", "CONFIRMATION_LINK_EXPIRED"),
        (False, "valid", None),
    ],
)
def test_link_code_and_expiry_validation(expired, stored, expected):
    auth = AuthService(Mock(spec=UserData), Settings())
    expires = datetime.now(UTC) + timedelta(minutes=-1 if expired else 1)
    code_hash = CredentialService.hash_one_time_code("valid") if stored else None
    if expected:
        with pytest.raises(AccountException) as error:
            auth.validate_code(
                "valid", code_hash, expires, "INVALID_CONFIRMATION_LINK", "CONFIRMATION_LINK_EXPIRED"
            )
        assert error.value.code == expected
    else:
        auth.validate_code(
            "valid", code_hash, expires, "INVALID_CONFIRMATION_LINK", "CONFIRMATION_LINK_EXPIRED"
        )


@pytest.mark.parametrize("key", [UUID(int=0), UUID(int=(1 << 128) - 1), UUID(int=1 << 127), uuid4()])
def test_payment_advisory_key_is_java_compatible(key):
    expected = (key.int >> 64) ^ (key.int & ((1 << 64) - 1))
    if expected >= 1 << 63:
        expected -= 1 << 64
    assert PaymentData.advisory_key(key) == expected


def test_decimal_response_stays_a_json_number_not_a_string():
    response = Responses({"price": Decimal("9999999999.99"), "text": "Москва"})
    assert b'"price":9999999999.99' in response.body
    assert "Москва" in response.body.decode()


def test_public_user_cannot_leak_security_fields():
    row = {
        "id": uuid4(),
        "username": "user",
        "first_name": None,
        "last_name": None,
        "email": "user@example.com",
        "phone": None,
        "user_status": "ACTIVE",
        "role": "USER",
        "password": "never-expose",
        "confirmation_code_hash": "secret",
        "reset_code_hash": "secret",
        "token_version": 5,
    }
    response = public_user(row)
    assert set(response) == {
        "id",
        "username",
        "firstName",
        "lastName",
        "email",
        "phone",
        "address",
        "userStatus",
        "role",
    }
    assert "never-expose" not in str(response)


def test_legacy_password_is_upgraded_after_successful_login():
    repository = Mock(spec=UserData)
    repository.database = MagicMock()
    repository.find_user_by_email.return_value = {
        "username": "legacy",
        "email": "legacy@example.com",
        "password": "ValidPass123",
    }
    auth = AuthService(repository, Settings())
    user = auth.authenticated_user("legacy@example.com", "ValidPass123")
    assert user["password"].startswith("$2a$10$")
    repository.database.connect.return_value.__enter__.return_value.execute.assert_called_once()


def test_expired_login_lockout_starts_a_new_failure_window():
    repository = Mock(spec=UserData)
    repository.find_user_by_email.return_value = None
    auth = AuthService(repository, Settings())
    auth.login_attempts["user@example.com"] = LoginAttempts(
        datetime.now(UTC) - timedelta(minutes=10), 5, datetime.now(UTC) - timedelta(minutes=1)
    )
    with pytest.raises(AccountException) as error:
        auth.authenticated_user("user@example.com", "WrongPass")
    assert error.value.status == 401
    assert auth.login_attempts["user@example.com"].count == 1


@pytest.mark.parametrize(
    "state,expected",
    [
        ("confirmed", "ACCOUNT_ALREADY_CONFIRMED"),
        ("invalid", "INVALID_CONFIRMATION_LINK"),
        ("expired", "CONFIRMATION_LINK_EXPIRED"),
        ("missing", "USER_NOT_FOUND"),
        ("valid", None),
    ],
)
def test_confirmation_validates_and_mutates_the_same_locked_row(state, expected):
    database = MagicMock()
    repository = UserData(database)
    user = {
        "id": uuid4(),
        "confirmed_at": datetime.now(UTC) if state == "confirmed" else None,
        "confirmation_code_hash": CredentialService.hash_one_time_code(
            "wrong" if state == "invalid" else "valid"
        ),
        "confirmation_expires_at": datetime.now(UTC) + timedelta(minutes=-1 if state == "expired" else 5),
    }
    connection = database.connect.return_value.__enter__.return_value
    updated = user | {"confirmed_at": datetime.now(UTC), "confirmation_expires_at": None}
    connection.execute.return_value.fetchone.side_effect = [None if state == "missing" else user, updated]
    auth = AuthService(repository, Settings())
    if expected:
        with pytest.raises(AccountException) as error:
            auth.confirm(user["id"], "valid")
        assert error.value.code == expected
        assert connection.execute.call_count == 1
    else:
        assert auth.confirm(user["id"], "valid") == updated
        assert "clock_timestamp()" in connection.execute.call_args_list[1].args[0]
    assert "FOR UPDATE" in connection.execute.call_args_list[0].args[0]


def test_resend_rechecks_current_confirmation_state_under_row_lock(monkeypatch):
    database = MagicMock()
    auth = AuthService(UserData(database), Settings())
    old = {"id": uuid4(), "confirmed_at": None}
    monkeypatch.setattr(auth, "authenticated_user", lambda email, password: old)
    connection = database.connect.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = old | {"confirmed_at": datetime.now(UTC)}
    with pytest.raises(AccountException) as error:
        auth.resend_confirmation("test@example.com", "ValidPass123")
    assert error.value.code == "ACCOUNT_ALREADY_CONFIRMED"
    assert connection.execute.call_count == 1
    assert "FOR UPDATE" in connection.execute.call_args.args[0]


@pytest.mark.parametrize("used,code", [(True, "RESET_LINK_ALREADY_USED"), (False, "RESET_STATE_CHANGED")])
def test_reset_conditional_update_failure_keeps_master_errors(used, code):
    repository = Mock(spec=UserData)
    repository.database = MagicMock()
    user = {
        "id": uuid4(),
        "reset_used_at": None,
        "reset_code_hash": CredentialService.hash_one_time_code("valid"),
        "reset_expires_at": datetime.now(UTC) + timedelta(minutes=5),
    }
    current = user | {"reset_used_at": datetime.now(UTC) if used else None}
    repository.find_user_by_id.return_value = current
    repository.database.connect.return_value.__enter__.return_value.execute.return_value.fetchone.side_effect = [
        user,
        None,
    ]
    auth = AuthService(repository, Settings())
    with pytest.raises(AccountException) as error:
        auth.reset_password("valid", "NewValidPass123")
    assert error.value.code == code


def test_environment_fallbacks_and_jdbc_url_are_compatible(monkeypatch):
    for name in (
        "PETSTORE_DB_USER",
        "PETSTORE_DB_PASSWORD",
        "PETSTORE_TOKEN_SECRET",
        "PETSTORE_PUBLIC_BASE_URL",
    ):
        monkeypatch.setenv(name, "   ")
    monkeypatch.setenv("PETSTORE_DB_URL", "jdbc:postgresql://localhost:5433/petstore")
    settings = Settings.from_env()
    assert settings.db_url == "postgresql://localhost:5433/petstore"
    assert settings.db_user == "petstore"
    assert settings.db_password == "petstore"
    assert settings.token_secret is None
    assert settings.public_base_url == "http://localhost:8080/api/v3"
