"""Registration, confirmation, password recovery and role-based authorization."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID

from petstore.config import Settings
from petstore.data.database import Row
from petstore.data.user_data import UserData
from petstore.model.requests import RegisterRequest
from petstore.notification.mail_service import MailService
from petstore.service.credential_service import CredentialService
from petstore.service.exceptions import AccountException
from petstore.service.token_service import TokenService
from petstore.utils.responses import public_user


@dataclass
class LoginAttempts:
    """Per-identifier failure window, matching the existing five-minute policy."""

    window_start: datetime
    count: int
    blocked_until: datetime | None = None


class AuthService:
    """Account business rules shared by the original controller responsibilities."""

    CONFIRMATION_TTL_HOURS = 24
    PASSWORD_RESET_TTL_MINUTES = 30

    def __init__(self, user_data: UserData, settings: Settings) -> None:
        """Configure compatible security services and an instance-scoped login limiter.

        :param user_data: PostgreSQL user repository.
        :param settings: URL, link-exposure and token configuration.
        """
        self.user_data = user_data
        self.settings = settings
        self.token_service = TokenService(settings.token_secret)
        self.credentials = CredentialService()
        self.mail = MailService(settings)
        self.login_attempts: dict[str, LoginAttempts] = {}
        self.attempts_lock = RLock()

    def register(self, request: RegisterRequest) -> Row:
        """Create a pending user and a 24-hour confirmation link.

        :param request: Validated account data.
        """
        assert request.password is not None
        code = self.credentials.new_one_time_code()
        expires = datetime.now(UTC) + timedelta(hours=self.CONFIRMATION_TTL_HOURS)
        user = self.user_data.add_pending_user(
            request,
            self.credentials.hash_password(request.password),
            self.credentials.hash_one_time_code(code),
            expires,
        )
        self.mail.send_link(user["id"], user["email"], user["username"], code, expires)
        return {
            "user": public_user(user),
            "confirmationUrl": self.confirmation_url(user["id"], code),
            "expiresAt": expires,
        }

    def required_user(self, user_id: UUID) -> Row:
        """Find an account or emit the existing account-specific 404.

        :param user_id: Account UUID.
        """
        user = self.user_data.find_user_by_id(user_id)
        if user is None:
            raise AccountException(404, "USER_NOT_FOUND", "User was not found")
        return user

    def confirmation_url(self, user_id: UUID, code: str) -> str:
        """Build a confirmation URL using the configured external API address.

        :param user_id: Account UUID.
        :param code: Raw confirmation code.
        """
        return f"{self.settings.public_base_url}/auth/confirm/{user_id}?code={code}"

    def validate_code(
        self, code: str, stored: str | None, expires: datetime | None, invalid: str, expired: str
    ) -> None:
        """Distinguish an invalid link from an expired valid code.

        :param code: Supplied code.
        :param stored: Persisted SHA-256 code hash.
        :param expires: Persisted deadline.
        :param invalid: Operation-specific invalid-link error.
        :param expired: Operation-specific expired-link error.
        """
        if not self.credentials.code_matches(code, stored):
            raise AccountException(400, invalid, "The one-time link is invalid")
        if expires is None or expires <= datetime.now(UTC):
            raise AccountException(410, expired, "The one-time link has expired")

    def confirm(self, user_id: UUID, code: str) -> Row:
        """Consume a matching unexpired confirmation code, preserving a blocked status.

        :param user_id: Account UUID from the path.
        :param code: One-time query parameter.
        """

        def validate(current: Row) -> None:
            """Check the current state and code after the repository acquires its lock.

            :param current: Locked account row.
            """
            self.require_unconfirmed_user(current)
            self.validate_code(
                code,
                current["confirmation_code_hash"],
                current["confirmation_expires_at"],
                "INVALID_CONFIRMATION_LINK",
                "CONFIRMATION_LINK_EXPIRED",
            )

        return self.user_data.confirm_user(user_id, validate)

    @staticmethod
    def require_unconfirmed_user(user: Row) -> None:
        """Reject an already-confirmed current row; missing rows are handled by the repository.

        :param user: Account row read under the confirmation transaction lock.
        """
        if user["confirmed_at"] is not None:
            raise AccountException(409, "ACCOUNT_ALREADY_CONFIRMED", "The account has already been confirmed")

    def authenticated_user(self, email: str, password: str) -> Row:
        """Authenticate credentials and enforce the existing failure-window policy.

        :param email: Submitted email, normalized only for rate-limit bookkeeping.
        :param password: Submitted password, never logged.
        """
        identifier = email.strip().lower()
        now = datetime.now(UTC)
        with self.attempts_lock:
            state = self.login_attempts.get(identifier)
            if state is not None:
                expires = state.blocked_until or state.window_start + timedelta(minutes=5)
                if expires <= now:
                    self.login_attempts.pop(identifier, None)
                elif state.blocked_until:
                    self.raise_rate_limited(state.blocked_until, now)
        user = self.user_data.find_user_by_email(email)
        valid = user is not None and self.credentials.password_matches(password, user["password"])
        if not valid:
            with self.attempts_lock:
                state = self.login_attempts.get(identifier)
                if state is None or (state.blocked_until or state.window_start + timedelta(minutes=5)) <= now:
                    state = LoginAttempts(now, 0)
                state.count += 1
                if state.count >= 5:
                    state.blocked_until = state.blocked_until or now + timedelta(minutes=5)
                self.login_attempts[identifier] = state
                if state.blocked_until:
                    self.raise_rate_limited(state.blocked_until, now)
            raise AccountException(401, "INVALID_CREDENTIALS", "Email or password is incorrect")
        assert user is not None
        with self.attempts_lock:
            self.login_attempts.pop(identifier, None)
        if not self.credentials.is_bcrypt(user["password"]):
            upgraded = self.credentials.hash_password(password)
            with self.user_data.database.connect() as connection:
                connection.execute(
                    "UPDATE users SET password = %s WHERE username = %s AND password = %s",
                    (upgraded, user["username"], user["password"]),
                )
            user["password"] = upgraded
        return user

    @staticmethod
    def raise_rate_limited(blocked_until: datetime, now: datetime) -> None:
        """Report the remaining lockout in whole minutes.

        :param blocked_until: Current lockout deadline.
        :param now: Current UTC time.
        """
        minutes = max(1, math.ceil((blocked_until - now).total_seconds() / 60))
        raise AccountException(
            429, "LOGIN_RATE_LIMITED", f"Too many failed login attempts. Try again in {minutes} minute(s)"
        )

    def login(self, email: str, password: str) -> Row:
        """Issue a token only for an active, unblocked account.

        :param email: Submitted email.
        :param password: Submitted password.
        """
        user = self.authenticated_user(email, password)
        self.ensure_account_can_authenticate(user)
        return {
            "access_token": self.token_service.issue_token(user),
            "token_type": "Bearer",
            "expires_in": TokenService.DEFAULT_TTL_SECONDS,
            "user": public_user(user),
        }

    @staticmethod
    def ensure_account_can_authenticate(user: Row) -> None:
        """Reject pending or blocked accounts with their original errors.

        :param user: Persisted account row.
        """
        if user["user_status"] == "PENDING":
            raise AccountException(403, "ACCOUNT_NOT_VERIFIED", "The account has not been confirmed")
        if user["user_status"] == "BLOCKED":
            raise AccountException(403, "ACCOUNT_BLOCKED", "The account is blocked")

    def authorize(self, authorization: str | None, *roles: str) -> Row:
        """Validate Bearer syntax, signature, current account state, role and token version.

        :param authorization: Incoming Authorization header.
        :param roles: Allowed role names; empty means any authenticated role.
        """
        if authorization is None or not authorization.strip():
            raise AccountException(401, "UNAUTHORIZED", "Bearer token is required")
        if not authorization.lower().startswith("bearer ") or not authorization[7:].strip():
            raise AccountException(401, "INVALID_TOKEN", "Authorization header must use the Bearer scheme")
        claims = self.token_service.validate(authorization[7:].strip())
        user = self.user_data.find_user_by_name(claims["sub"])
        if user is None or user["role"] != claims["role"]:
            raise AccountException(401, "INVALID_TOKEN", "Access token is invalid")
        self.ensure_account_can_authenticate(user)
        if user["token_version"] != claims["ver"]:
            raise AccountException(401, "INVALID_TOKEN", "Access token is invalid")
        if roles and user["role"] not in roles:
            raise AccountException(
                403, "FORBIDDEN", "The current role is not allowed to perform this operation"
            )
        return user

    def resend_confirmation(self, email: str, password: str) -> Row:
        """Replace the code so every earlier confirmation link becomes invalid.

        :param email: Account email.
        :param password: Credentials required to regenerate the link.
        """
        user = self.authenticated_user(email, password)
        if user["confirmed_at"] is not None:
            raise AccountException(409, "ACCOUNT_ALREADY_CONFIRMED", "The account has already been confirmed")
        code = self.credentials.new_one_time_code()
        expires = datetime.now(UTC) + timedelta(hours=self.CONFIRMATION_TTL_HOURS)
        self.user_data.set_confirmation_link(
            user["id"], self.credentials.hash_one_time_code(code), expires, self.require_unconfirmed_user
        )
        self.mail.send_link(user["id"], user["email"], user["username"], code, expires)
        return {"confirmationUrl": self.confirmation_url(user["id"], code), "expiresAt": expires}

    def forgot_password(self, email: str) -> Row:
        """Issue a thirty-minute reset code and honor PETSTORE_EXPOSE_TEST_LINKS.

        :param email: Account email.
        """
        user = self.user_data.find_user_by_email(email)
        if user is None:
            raise AccountException(404, "USER_NOT_FOUND", "A user with this email was not found")
        code = self.credentials.new_one_time_code()
        expires = datetime.now(UTC) + timedelta(minutes=self.PASSWORD_RESET_TTL_MINUTES)
        with self.user_data.database.connect() as connection:
            connection.execute(
                "UPDATE users SET reset_code_hash = %s, reset_expires_at = %s, reset_used_at = NULL WHERE id = %s",
                (self.credentials.hash_one_time_code(code), expires, user["id"]),
            )
        self.mail.send_link(user["id"], user["email"], user["username"], code, expires, reset=True)
        url = (
            f"{self.settings.public_base_url}/auth/password/reset?code={code}"
            if self.settings.expose_test_links
            else None
        )
        return {"resetUrl": url, "expiresAt": expires}

    def reset_password(self, code: str, new_password: str) -> None:
        """Consume a reset code once and invalidate every earlier access token.

        :param code: Query parameter from the reset link.
        :param new_password: Validated replacement password.
        """
        hashed = self.credentials.hash_one_time_code(code)
        with self.user_data.database.connect() as connection:
            user = connection.execute("SELECT * FROM users WHERE reset_code_hash = %s", (hashed,)).fetchone()
        if user is None:
            raise AccountException(400, "INVALID_RESET_LINK", "The one-time link is invalid")
        if user["reset_used_at"] is not None:
            raise AccountException(
                409, "RESET_LINK_ALREADY_USED", "The password reset link has already been used"
            )
        self.validate_code(
            code,
            user["reset_code_hash"],
            user["reset_expires_at"],
            "INVALID_RESET_LINK",
            "RESET_LINK_EXPIRED",
        )
        password_hash = self.credentials.hash_password(new_password)
        with self.user_data.database.connect() as connection:
            row = connection.execute(
                "UPDATE users SET password = %s, reset_expires_at = NULL, reset_used_at = CURRENT_TIMESTAMP, token_version = token_version + 1 WHERE id = %s AND reset_code_hash = %s AND reset_used_at IS NULL AND reset_expires_at > CURRENT_TIMESTAMP RETURNING *",
                (password_hash, user["id"], hashed),
            ).fetchone()
        if row is None:
            current = self.required_user(user["id"])
            if current["reset_used_at"] is not None and self.credentials.code_matches(
                code, current["reset_code_hash"]
            ):
                raise AccountException(
                    409, "RESET_LINK_ALREADY_USED", "The password reset link has already been used"
                )
            self.validate_code(
                code,
                current["reset_code_hash"],
                current["reset_expires_at"],
                "INVALID_RESET_LINK",
                "RESET_LINK_EXPIRED",
            )
            raise AccountException(
                409, "RESET_STATE_CHANGED", "The password reset state changed; request a new link"
            )
        with self.attempts_lock:
            self.login_attempts.pop(row["email"].strip().lower(), None)

    def set_blocked(self, actor: Row, user_id: UUID, blocked: bool) -> Row:
        """Block or restore a non-administrator account without allowing self-management.

        :param actor: Authorized administrator.
        :param user_id: Target UUID.
        :param blocked: True to block, false to unblock.
        """
        target = self.required_user(user_id)
        if actor["id"] == user_id or target["role"] == "ADMIN":
            raise AccountException(
                403, "ADMIN_ACCOUNT_PROTECTED", "Administrator accounts cannot be managed by this operation"
            )
        if blocked and target["user_status"] == "BLOCKED":
            raise AccountException(409, "INVALID_STATUS_TRANSITION", "The account is already blocked")
        if not blocked and target["user_status"] != "BLOCKED":
            raise AccountException(409, "INVALID_STATUS_TRANSITION", "The account is not blocked")
        state = "BLOCKED" if blocked else "PENDING" if target["confirmed_at"] is None else "ACTIVE"
        with self.user_data.database.connect() as connection:
            row = connection.execute(
                "UPDATE users SET user_status = %s::account_status, token_version = token_version + %s WHERE id = %s AND user_status = %s::account_status RETURNING *",
                (state, int(blocked), user_id, target["user_status"]),
            ).fetchone()
        if row is None:
            action = "blocked" if blocked else "unblocked"
            raise AccountException(
                409, "INVALID_STATUS_TRANSITION", f"The account status changed before it could be {action}"
            )
        return row
