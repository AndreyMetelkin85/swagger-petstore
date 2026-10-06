"""User persistence retaining the original lifecycle and protected-account rules."""

from collections.abc import Callable
from datetime import datetime
from typing import Any, LiteralString
from uuid import UUID

from psycopg import sql
from psycopg.errors import UniqueViolation

from petstore.data.database import Database, DbConnection, Row
from petstore.model.requests import AdminUserUpdateRequest, RegisterRequest, UserUpdateRequest
from petstore.service.exceptions import AccountException


class UserData:
    """PostgreSQL-backed user repository, with no password fields in public responses."""

    def __init__(self, database: Database) -> None:
        """Use the application's bounded connection pool.

        :param database: PostgreSQL connection factory.
        """
        self.database = database

    def find_user_by_id(self, user_id: UUID) -> Row | None:
        """Find an account by its existing UUID.

        :param user_id: Persisted account identifier.
        """
        with self.database.connect() as connection:
            return connection.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()

    def find_user_by_name(self, username: str) -> Row | None:
        """Find a case-sensitive username, matching the original unique constraint.

        :param username: Account username.
        """
        with self.database.connect() as connection:
            return connection.execute("SELECT * FROM users WHERE username = %s", (username,)).fetchone()

    def find_user_by_email(self, email: str) -> Row | None:
        """Find a case-insensitive email without silently changing stored values.

        :param email: Submitted email.
        """
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(%s)", (email,)
            ).fetchone()

    @staticmethod
    def locked_user(connection: DbConnection, user_id: UUID) -> Row:
        """Acquire a user row lock inside the caller's transaction.

        :param connection: Current transaction connection.
        :param user_id: Target UUID.
        """
        user = connection.execute("SELECT * FROM users WHERE id = %s FOR UPDATE", (user_id,)).fetchone()
        if user is None:
            raise AccountException(404, "USER_NOT_FOUND", "User was not found")
        return user

    def add_pending_user(
        self, request: RegisterRequest, password_hash: str, code_hash: str, expires: datetime
    ) -> Row:
        """Create a pending account without granting client-supplied privileges.

        :param request: Validated registration data.
        :param password_hash: Bcrypt hash.
        :param code_hash: Confirmation code hash.
        :param expires: Confirmation deadline.
        """
        address = request.address
        try:
            with self.database.connect() as connection:
                row = connection.execute(
                    """INSERT INTO users (username, first_name, last_name, email, password, phone,
                       user_status, role, confirmed_at, confirmation_code_hash, confirmation_expires_at,
                       address_city, address_street, address_house, address_apartment, address_postal_code)
                       VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', 'USER', NULL, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *""",
                    (
                        request.username,
                        request.first_name,
                        request.last_name,
                        request.email,
                        password_hash,
                        request.phone,
                        code_hash,
                        expires,
                        address.city if address else None,
                        address.street if address else None,
                        address.house if address else None,
                        address.apartment if address else None,
                        address.postal_code if address else None,
                    ),
                ).fetchone()
                assert row is not None
                return row
        except UniqueViolation as exc:
            raise AccountException(
                409,
                "USER_ALREADY_EXISTS",
                "A user with this username or email already exists",
                self.registration_conflicts(request.username, request.email),
            ) from exc

    def registration_conflicts(self, username: str | None, email: str | None) -> list[Row]:
        """Read both conflicting fields in one snapshot after a failed insertion.

        :param username: Submitted username, not echoed in the response.
        :param email: Submitted email, compared case-insensitively and not echoed.
        """
        with self.database.connect() as connection:
            conflicts = connection.execute(
                """SELECT EXISTS (SELECT 1 FROM users WHERE username = %s) AS username_conflict,
                   EXISTS (SELECT 1 FROM users WHERE LOWER(email) = LOWER(%s)) AS email_conflict""",
                (username, email),
            ).fetchone()
            assert conflicts is not None
            return [
                {"field": field, "message": f"A user with this {field} already exists"}
                for field in ("username", "email")
                if conflicts[field + "_conflict"]
            ]

    def _update_confirmation(
        self,
        user_id: UUID,
        validate: Callable[[Row], None],
        query: LiteralString,
        parameters: tuple[Any, ...],
    ) -> Row:
        """Validate and mutate the same locked row, serializing confirm/resend/deletion.

        :param user_id: Account UUID.
        :param validate: Business checks performed after acquiring the row lock.
        :param query: Static update statement.
        :param parameters: Bound update values.
        """
        with self.database.connect() as connection:
            validate(self.locked_user(connection, user_id))
            updated = connection.execute(query, parameters).fetchone()
            if updated is None:
                raise RuntimeError("Locked confirmation row disappeared")
            return updated

    def confirm_user(self, user_id: UUID, validate: Callable[[Row], None]) -> Row:
        """Consume a confirmation link after validating its current locked state.

        :param user_id: Account UUID.
        :param validate: Confirmation-code, expiry and state checks.
        """
        return self._update_confirmation(
            user_id,
            validate,
            """UPDATE users SET confirmed_at = clock_timestamp(), confirmation_expires_at = NULL,
               user_status = CASE WHEN user_status = 'BLOCKED' THEN 'BLOCKED'::account_status
               ELSE 'ACTIVE'::account_status END WHERE id = %s RETURNING *""",
            (user_id,),
        )

    def set_confirmation_link(
        self, user_id: UUID, code_hash: str, expires: datetime, validate: Callable[[Row], None]
    ) -> Row:
        """Replace a link only while the current locked account is still unconfirmed.

        :param user_id: Account UUID.
        :param code_hash: New SHA-256 code hash.
        :param expires: New deadline.
        :param validate: Current account-state check under the row lock.
        """
        return self._update_confirmation(
            user_id,
            validate,
            "UPDATE users SET confirmation_code_hash = %s, confirmation_expires_at = %s WHERE id = %s RETURNING *",
            (code_hash, expires, user_id),
        )

    def update_user(self, user: Row, request: UserUpdateRequest) -> Row:
        """Apply a partial update and distinguish missing address from explicit null.

        :param user: Authorized account row.
        :param request: Validated profile changes.
        """
        present = "address" in request.model_fields_set
        address = request.address
        with self.database.connect() as connection:
            row = connection.execute(
                """UPDATE users SET first_name = COALESCE(%s, first_name), last_name = COALESCE(%s, last_name),
                   phone = COALESCE(%s, phone),
                   address_city = CASE WHEN %s THEN %s ELSE address_city END,
                   address_street = CASE WHEN %s THEN %s ELSE address_street END,
                   address_house = CASE WHEN %s THEN %s ELSE address_house END,
                   address_apartment = CASE WHEN %s THEN %s ELSE address_apartment END,
                   address_postal_code = CASE WHEN %s THEN %s ELSE address_postal_code END
                   WHERE username = %s RETURNING *""",
                (
                    request.first_name,
                    request.last_name,
                    request.phone,
                    present,
                    address.city if address else None,
                    present,
                    address.street if address else None,
                    present,
                    address.house if address else None,
                    present,
                    address.apartment if address else None,
                    present,
                    address.postal_code if address else None,
                    user["username"],
                ),
            ).fetchone()
            if row is None:
                raise AccountException(404, "USER_NOT_FOUND", "User was not found")
            return row

    def update_user_as_admin(self, user_id: UUID, request: AdminUserUpdateRequest) -> Row:
        """Serialize administrator changes, protect the last admin and invalidate old tokens.

        :param user_id: Target account UUID.
        :param request: Validated full profile.
        """
        assert request.email is not None
        email = request.email.strip().lower()
        try:
            with self.database.connect() as connection:
                connection.execute("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE")
                current = self.locked_user(connection, user_id)
                checks: list[tuple[LiteralString, Any, str, str]] = [
                    ("username", request.username, "USERNAME_ALREADY_EXISTS", "username"),
                    ("LOWER(email)", email, "EMAIL_ALREADY_EXISTS", "email"),
                ]
                for column, value, code, label in checks:
                    query = sql.SQL("SELECT id FROM users WHERE {} = %s AND id <> %s").format(sql.SQL(column))
                    owner = connection.execute(query, (value, user_id)).fetchone()
                    if owner:
                        raise AccountException(409, code, f"A user with this {label} already exists")
                if current["role"] == "ADMIN" and request.role != "ADMIN":
                    count = connection.execute(
                        "SELECT COUNT(*) AS total FROM users WHERE role = 'ADMIN'"
                    ).fetchone()
                    if count is not None and count["total"] <= 1:
                        raise AccountException(
                            409, "LAST_ADMIN_PROTECTED", "The last administrator cannot be demoted"
                        )
                if (
                    current["role"] != "ADMIN"
                    and request.role == "ADMIN"
                    and current["user_status"] != "ACTIVE"
                ):
                    raise AccountException(
                        409, "INVALID_ROLE_TRANSITION", "Only an active user can be promoted to administrator"
                    )
                changed = (current["email"] or "").lower() != email
                address = request.address
                row = connection.execute(
                    """UPDATE users SET username = %s, first_name = %s, last_name = %s, email = %s, phone = %s,
                       address_city = %s, address_street = %s, address_house = %s, address_apartment = %s,
                       address_postal_code = %s, role = %s,
                       confirmation_code_hash = CASE WHEN %s THEN NULL ELSE confirmation_code_hash END,
                       confirmation_expires_at = CASE WHEN %s THEN NULL ELSE confirmation_expires_at END,
                       reset_code_hash = CASE WHEN %s THEN NULL ELSE reset_code_hash END,
                       reset_expires_at = CASE WHEN %s THEN NULL ELSE reset_expires_at END,
                       reset_used_at = CASE WHEN %s THEN NULL ELSE reset_used_at END,
                       token_version = token_version + 1 WHERE id = %s RETURNING *""",
                    (
                        request.username,
                        request.first_name,
                        request.last_name,
                        email,
                        request.phone,
                        address.city if address else None,
                        address.street if address else None,
                        address.house if address else None,
                        address.apartment if address else None,
                        address.postal_code if address else None,
                        request.role,
                        changed,
                        changed,
                        changed,
                        changed,
                        changed,
                        user_id,
                    ),
                ).fetchone()
                assert row is not None
                return row
        except UniqueViolation as exc:
            email_conflict = exc.diag.constraint_name == "uq_users_email_lower"
            label = "email" if email_conflict else "username"
            raise AccountException(
                409,
                "EMAIL_ALREADY_EXISTS" if email_conflict else "USERNAME_ALREADY_EXISTS",
                f"A user with this {label} already exists",
            ) from exc

    def find_all(self) -> list[Row]:
        """List accounts in the same deterministic UUID order."""
        with self.database.connect() as connection:
            return connection.execute("SELECT * FROM users ORDER BY id").fetchall()

    def delete_user(self, actor: Row, user_id: UUID) -> None:
        """Delete only an unprotected account without order history.

        :param actor: Authorized administrator.
        :param user_id: Target account UUID.
        """
        with self.database.connect() as connection:
            user = self.locked_user(connection, user_id)
            if actor["id"] == user_id or user["role"] == "ADMIN":
                raise AccountException(
                    403, "ADMIN_ACCOUNT_PROTECTED", "Administrator accounts cannot be deleted"
                )
            if connection.execute(
                "SELECT 1 FROM protected_user_accounts WHERE user_id = %s", (user_id,)
            ).fetchone():
                raise AccountException(
                    403, "DEMO_ACCOUNT_PROTECTED", "The demonstration user account cannot be deleted"
                )
            if connection.execute(
                "SELECT 1 FROM store_orders WHERE owner_user_id = %s", (user_id,)
            ).fetchone():
                raise AccountException(
                    409, "USER_HAS_ORDERS", "Delete the user's orders before deleting the account"
                )
            connection.execute("DELETE FROM api_idempotency WHERE user_id=%s", (user_id,))
            connection.execute("DELETE FROM cart_lines WHERE user_id=%s", (user_id,))
            connection.execute("DELETE FROM carts WHERE user_id=%s", (user_id,))
            connection.execute("DELETE FROM users WHERE id = %s", (user_id,))
