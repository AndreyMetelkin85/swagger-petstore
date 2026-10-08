"""Бизнес-правила и согласование операций приложения."""

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
    """Окно неуспешных входов для идентификатора по действующему правилу пяти минут."""

    window_start: datetime
    count: int
    blocked_until: datetime | None = None


class AuthService:
    """Бизнес-правила регистрации, подтверждения, входа и восстановления."""

    CONFIRMATION_TTL_HOURS = 24
    PASSWORD_RESET_TTL_MINUTES = 30

    def __init__(self, user_data: UserData, settings: Settings) -> None:
        """Настраивает безопасность и отдельный для приложения ограничитель попыток входа.

        :param user_data: Репозиторий пользователей с общим пулом соединений.
        :param settings: Настройки приложения и его инфраструктурных подключений.
        :return: Ничего не возвращает.
        """
        self.user_data = user_data
        self.settings = settings
        self.token_service = TokenService(settings.token_secret)
        self.credentials = CredentialService()
        self.mail = MailService(settings)
        self.login_attempts: dict[str, LoginAttempts] = {}
        self.attempts_lock = RLock()

    def register(self, request: RegisterRequest) -> Row:
        """Создаёт неподтверждённого пользователя и ссылку подтверждения на 24 часа.

        :param request: Разобранный запрос операции; исходные секреты не записываются в логи.
        :return: Результат операции типа Row.
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
        """Возвращает аккаунт либо действующую ошибку отсутствующего пользователя.

        :param user_id: UUID целевого пользователя.
        :return: Результат операции типа Row.
        """
        user = self.user_data.find_user_by_id(user_id)
        if user is None:
            raise AccountException(404, "USER_NOT_FOUND", "User was not found")
        return user

    def confirmation_url(self, user_id: UUID, code: str) -> str:
        """Строит ссылку подтверждения на основе внешнего адреса API.

        :param user_id: UUID целевого пользователя.
        :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
        :return: Строковый результат описанной операции.
        """
        return f"{self.settings.public_base_url}/auth/confirm/{user_id}?code={code}"

    def validate_code(
        self, code: str, stored: str | None, expires: datetime | None, invalid: str, expired: str
    ) -> None:
        """Различает неверную ссылку и корректный код с истёкшим сроком.

        :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
        :param stored: Сохранённое значение для сравнения.
        :param expires: Время окончания действия ссылки или резерва.
        :param invalid: Код ошибки для неверной ссылки.
        :param expired: Код ошибки для истёкшей ссылки.
        :return: Ничего не возвращает.
        """
        if not self.credentials.code_matches(code, stored):
            raise AccountException(400, invalid, "The one-time link is invalid")
        if expires is None or expires <= datetime.now(UTC):
            raise AccountException(410, expired, "The one-time link has expired")

    def confirm(self, user_id: UUID, code: str) -> Row:
        """Однократно применяет неистёкший код, сохраняя блокировку аккаунта.

        :param user_id: UUID целевого пользователя.
        :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
        :return: Результат операции типа Row.
        """

        def validate(current: Row) -> None:
            """Проверяет состояние и код после получения репозиторием блокировки строки.

            :param current: Текущее состояние или версия записи.
            :return: Ничего не возвращает.
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
        """Отклоняет уже подтверждённую строку; отсутствие пользователя обрабатывает репозиторий.

        :param user: Строка пользователя, полученная из базы данных.
        :return: Ничего не возвращает.
        """
        if user["confirmed_at"] is not None:
            raise AccountException(409, "ACCOUNT_ALREADY_CONFIRMED", "The account has already been confirmed")

    def authenticated_user(self, email: str, password: str) -> Row:
        """Проверяет учётные данные и применяет ограничение неуспешных попыток входа.

        :param email: Email аккаунта; не включается в диагностические логи.
        :param password: Пароль для проверки или хеширования; не сохраняется в логах.
        :return: Результат операции типа Row.
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
        """Формирует ошибку ограничения с оставшимся временем блокировки в целых минутах.

        :param blocked_until: Время окончания ограничения входа.
        :param now: Текущее время для проверки срока действия.
        :return: Ничего не возвращает.
        """
        minutes = max(1, math.ceil((blocked_until - now).total_seconds() / 60))
        raise AccountException(
            429, "LOGIN_RATE_LIMITED", f"Too many failed login attempts. Try again in {minutes} minute(s)"
        )

    def login(self, email: str, password: str) -> Row:
        """Выдаёт токен только активному незаблокированному аккаунту.

        :param email: Email аккаунта; не включается в диагностические логи.
        :param password: Пароль для проверки или хеширования; не сохраняется в логах.
        :return: Результат операции типа Row.
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
        """Отклоняет неподтверждённые и заблокированные аккаунты с действующими кодами ошибок.

        :param user: Строка пользователя, полученная из базы данных.
        :return: Ничего не возвращает.
        """
        if user["user_status"] == "PENDING":
            raise AccountException(403, "ACCOUNT_NOT_VERIFIED", "The account has not been confirmed")
        if user["user_status"] == "BLOCKED":
            raise AccountException(403, "ACCOUNT_BLOCKED", "The account is blocked")

    def authorize(self, authorization: str | None, *roles: str) -> Row:
        """Проверяет Bearer, подпись, состояние аккаунта, роль и версию токена.

        :param authorization: Значение заголовка Authorization входящего запроса.
        :param roles: Роли, которым разрешена операция; пустой список разрешает любой авторизованный аккаунт.
        :return: Результат операции типа Row.
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
        """Заменяет код подтверждения; все прежние ссылки становятся недействительными.

        :param email: Email аккаунта; не включается в диагностические логи.
        :param password: Пароль для проверки или хеширования; не сохраняется в логах.
        :return: Результат операции типа Row.
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
        """Выдаёт код восстановления на 30 минут с учётом PETSTORE_EXPOSE_TEST_LINKS.

        :param email: Email аккаунта; не включается в диагностические логи.
        :return: Результат операции типа Row.
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
        """Однократно применяет код восстановления и отзывает все прежние токены доступа.

        :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
        :param new_password: Новый пароль, проверенный правилами операции.
        :return: Ничего не возвращает.
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
        """Блокирует или восстанавливает обычный аккаунт, запрещая управление собственным доступом.

        :param actor: Авторизованный пользователь, выполняющий операцию.
        :param user_id: UUID целевого пользователя.
        :param blocked: Новое состояние блокировки аккаунта.
        :return: Результат операции типа Row.
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
