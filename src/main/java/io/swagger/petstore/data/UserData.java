package io.swagger.petstore.data;

import io.swagger.petstore.model.AdminUserUpdateRequest;
import io.swagger.petstore.model.AccountStatus;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;
import io.swagger.petstore.model.UserUpdateRequest;
import org.postgresql.util.PSQLException;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.UUID;

/** PostgreSQL-backed user repository for local API testing. */
public class UserData {
    private static final String COLUMNS =
            "id, username, first_name, last_name, email, password, phone, "
            + "user_status, role, confirmed_at, confirmation_code_hash, "
            + "confirmation_expires_at, reset_code_hash, reset_expires_at, "
            + "reset_used_at, token_version";

    public User findUserByName(final String username) {
        return findOne("username = ?", username);
    }

    public User findUserById(final UUID id) {
        if (id == null) {
            return null;
        }
        final String sql = "SELECT " + COLUMNS + " FROM users WHERE id = ?";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, id);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("find user by id", exception);
        }
    }

    public User findUserByEmail(final String email) {
        if (email == null) {
            return null;
        }
        final String sql = "SELECT " + COLUMNS + " FROM users WHERE LOWER(email) = LOWER(?)";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, email);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("find user by email", exception);
        }
    }

    private User findOne(final String condition, final String value) {
        if (value == null) {
            return null;
        }
        final String sql = "SELECT " + COLUMNS + " FROM users WHERE " + condition;
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, value);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("find user", exception);
        }
    }

    public boolean addPendingUserIfAbsent(final User user, final String confirmationHash,
                                           final Date confirmationExpiresAt) {
        user.setUserStatus(AccountStatus.PENDING);
        user.setConfirmedAt(null);
        return insertUser(user, confirmationHash, confirmationExpiresAt);
    }

    private boolean insertUser(final User user, final String confirmationHash,
                               final Date confirmationExpiresAt) {
        if (user == null || user.getUsername() == null) {
            return false;
        }
        if (user.getRole() == null) {
            user.setRole(Role.USER);
        }
        final boolean suppliedId = user.getId() != null;
        final String columns = "username, first_name, last_name, email, password, phone, "
                + "user_status, role, confirmed_at, confirmation_code_hash, confirmation_expires_at";
        final String values = "?, ?, ?, ?, ?, ?, CAST(? AS account_status), ?, ?, ?, ?";
        final String sql = suppliedId
                ? "INSERT INTO users (id, " + columns + ") VALUES (?, " + values + ") RETURNING " + COLUMNS
                : "INSERT INTO users (" + columns + ") VALUES (" + values + ") RETURNING " + COLUMNS;
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            int index = 1;
            if (suppliedId) {
                statement.setObject(index++, user.getId());
            }
            bindUser(statement, index, user, confirmationHash, confirmationExpiresAt);
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                copySecurity(map(result), user);
            }
            return true;
        } catch (SQLException exception) {
            if (Database.isUniqueViolation(exception)) {
                return false;
            }
            throw Database.failure("create user", exception);
        }
    }

    public User updateUser(final String username, final UserUpdateRequest update) {
        if (username == null || update == null) {
            return null;
        }
        final String sql = "UPDATE users SET "
                + "first_name = COALESCE(?, first_name), last_name = COALESCE(?, last_name), "
                + "phone = COALESCE(?, phone) "
                + "WHERE username = ? RETURNING " + COLUMNS;
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, update.getFirstName());
            statement.setString(2, update.getLastName());
            statement.setString(3, update.getPhone());
            statement.setString(4, username);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("update user", exception);
        }
    }

    public User updateUserAsAdmin(final UUID userId, final AdminUserUpdateRequest update,
                                  final String normalizedEmail) {
        if (userId == null || update == null) {
            return null;
        }
        try (Connection connection = Database.connect()) {
            connection.setAutoCommit(false);
            try {
                try (Statement lock = connection.createStatement()) {
                    lock.execute("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE");
                }
                final User current = findUserById(connection, userId);
                if (current == null) {
                    connection.rollback();
                    return null;
                }
                if (current.getRole() == Role.ADMIN && update.getRole() != Role.ADMIN
                        && countAdministrators(connection) <= 1) {
                    throw new LastAdministratorException();
                }
                if (current.getRole() != Role.ADMIN && update.getRole() == Role.ADMIN
                        && current.getUserStatus() != AccountStatus.ACTIVE) {
                    throw new InvalidRoleTransitionException();
                }
                final boolean emailChanged = current.getEmail() == null
                        || !current.getEmail().equalsIgnoreCase(normalizedEmail);
                final String sql = "UPDATE users SET username = ?, first_name = ?, last_name = ?, "
                        + "email = ?, phone = ?, role = ?, "
                        + "confirmation_code_hash = CASE WHEN ? THEN NULL ELSE confirmation_code_hash END, "
                        + "confirmation_expires_at = CASE WHEN ? THEN NULL ELSE confirmation_expires_at END, "
                        + "reset_code_hash = CASE WHEN ? THEN NULL ELSE reset_code_hash END, "
                        + "reset_expires_at = CASE WHEN ? THEN NULL ELSE reset_expires_at END, "
                        + "reset_used_at = CASE WHEN ? THEN NULL ELSE reset_used_at END, "
                        + "token_version = token_version + 1 WHERE id = ? RETURNING " + COLUMNS;
                final User result;
                try (PreparedStatement statement = connection.prepareStatement(sql)) {
                    statement.setString(1, update.getUsername());
                    statement.setString(2, update.getFirstName());
                    statement.setString(3, update.getLastName());
                    statement.setString(4, normalizedEmail);
                    statement.setString(5, update.getPhone());
                    statement.setString(6, update.getRole().name());
                    for (int index = 7; index <= 11; index++) {
                        statement.setBoolean(index, emailChanged);
                    }
                    statement.setObject(12, userId);
                    try (ResultSet rows = statement.executeQuery()) {
                        result = rows.next() ? map(rows) : null;
                    }
                }
                connection.commit();
                return result;
            } catch (SQLException | RuntimeException exception) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    exception.addSuppressed(rollbackFailure);
                }
                throw exception;
            }
        } catch (SQLException exception) {
            if (Database.isUniqueViolation(exception)) {
                final String constraint = uniqueConstraint(exception);
                if ("uq_users_email_lower".equals(constraint)) {
                    throw new EmailAlreadyExistsException();
                }
                if ("users_username_key".equals(constraint)) {
                    throw new UsernameAlreadyExistsException();
                }
            }
            throw Database.failure("update user as administrator", exception);
        }
    }

    public boolean replacePasswordIfCurrent(final String username, final String currentPassword,
                                             final String passwordHash) {
        final String sql = "UPDATE users SET password = ? WHERE username = ? AND password = ?";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, passwordHash);
            statement.setString(2, username);
            statement.setString(3, currentPassword);
            return statement.executeUpdate() > 0;
        } catch (SQLException exception) {
            throw Database.failure("upgrade password hash", exception);
        }
    }

    public User setConfirmationLink(final UUID userId, final String hash, final Date expiresAt) {
        final String sql = "UPDATE users SET confirmation_code_hash = ?, confirmation_expires_at = ? "
                + "WHERE id = ? AND confirmed_at IS NULL RETURNING " + COLUMNS;
        return updateLink(sql, userId, hash, expiresAt, "set confirmation link");
    }

    public User confirmUser(final UUID userId, final String expectedHash) {
        final String sql = "UPDATE users SET confirmed_at = CURRENT_TIMESTAMP, "
                + "confirmation_expires_at = NULL, "
                + "user_status = CASE WHEN user_status = 'BLOCKED' THEN 'BLOCKED'::account_status "
                + "ELSE 'ACTIVE'::account_status END "
                + "WHERE id = ? AND confirmed_at IS NULL AND confirmation_code_hash = ? "
                + "AND confirmation_expires_at > CURRENT_TIMESTAMP RETURNING " + COLUMNS;
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, userId);
            statement.setString(2, expectedHash);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("confirm user", exception);
        }
    }

    public User setResetLink(final UUID userId, final String hash, final Date expiresAt) {
        final String sql = "UPDATE users SET reset_code_hash = ?, reset_expires_at = ?, reset_used_at = NULL "
                + "WHERE id = ? RETURNING " + COLUMNS;
        return updateLink(sql, userId, hash, expiresAt, "set password reset link");
    }

    public User resetPassword(final UUID userId, final String expectedHash, final String passwordHash) {
        final String sql = "UPDATE users SET password = ?, reset_expires_at = NULL, "
                + "reset_used_at = CURRENT_TIMESTAMP, token_version = token_version + 1 "
                + "WHERE id = ? AND reset_code_hash = ? AND reset_used_at IS NULL "
                + "AND reset_expires_at > CURRENT_TIMESTAMP RETURNING " + COLUMNS;
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, passwordHash);
            statement.setObject(2, userId);
            statement.setString(3, expectedHash);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("reset password", exception);
        }
    }

    public User setStatus(final UUID userId, final AccountStatus expectedStatus,
                          final AccountStatus status, final boolean invalidateTokens) {
        final String sql = "UPDATE users SET user_status = CAST(? AS account_status), "
                + "token_version = token_version + ? WHERE id = ? "
                + "AND user_status = CAST(? AS account_status) RETURNING " + COLUMNS;
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, status.name());
            statement.setInt(2, invalidateTokens ? 1 : 0);
            statement.setObject(3, userId);
            statement.setString(4, expectedStatus.name());
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("change account status", exception);
        }
    }

    private User updateLink(final String sql, final UUID userId, final String hash,
                            final Date expiresAt, final String operation) {
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, hash);
            statement.setTimestamp(2, new Timestamp(expiresAt.getTime()));
            statement.setObject(3, userId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure(operation, exception);
        }
    }

    public List<User> findAll() {
        final List<User> users = new ArrayList<>();
        try (Connection connection = Database.connect();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT " + COLUMNS + " FROM users ORDER BY id")) {
            while (result.next()) {
                users.add(map(result));
            }
            return users;
        } catch (SQLException exception) {
            throw Database.failure("list users", exception);
        }
    }

    private static void bindUser(final PreparedStatement statement, final int start, final User user,
                                 final String confirmationHash, final Date confirmationExpiresAt)
            throws SQLException {
        int index = start;
        statement.setString(index++, user.getUsername());
        statement.setString(index++, user.getFirstName());
        statement.setString(index++, user.getLastName());
        statement.setString(index++, user.getEmail());
        statement.setString(index++, user.getPassword());
        statement.setString(index++, user.getPhone());
        statement.setString(index++, user.getUserStatus().name());
        statement.setString(index++, user.getRole().name());
        setTimestamp(statement, index++, user.getConfirmedAt());
        statement.setString(index++, confirmationHash);
        setTimestamp(statement, index, confirmationExpiresAt);
    }

    private static User map(final ResultSet result) throws SQLException {
        final User user = createUser((UUID) result.getObject("id"), result.getString("username"),
                result.getString("first_name"), result.getString("last_name"),
                result.getString("email"), result.getString("password"),
                result.getString("phone"), AccountStatus.valueOf(result.getString("user_status")),
                Role.valueOf(result.getString("role")));
        user.setConfirmedAt(toDate(result.getTimestamp("confirmed_at")));
        user.setConfirmationCodeHash(result.getString("confirmation_code_hash"));
        user.setConfirmationExpiresAt(toDate(result.getTimestamp("confirmation_expires_at")));
        user.setResetCodeHash(result.getString("reset_code_hash"));
        user.setResetExpiresAt(toDate(result.getTimestamp("reset_expires_at")));
        user.setResetUsedAt(toDate(result.getTimestamp("reset_used_at")));
        user.setTokenVersion(result.getInt("token_version"));
        return user;
    }

    private static void copySecurity(final User source, final User target) {
        target.setId(source.getId());
        target.setUserStatus(source.getUserStatus());
        target.setConfirmedAt(source.getConfirmedAt());
        target.setConfirmationCodeHash(source.getConfirmationCodeHash());
        target.setConfirmationExpiresAt(source.getConfirmationExpiresAt());
        target.setResetCodeHash(source.getResetCodeHash());
        target.setResetExpiresAt(source.getResetExpiresAt());
        target.setResetUsedAt(source.getResetUsedAt());
        target.setTokenVersion(source.getTokenVersion());
    }

    private static Date toDate(final Timestamp timestamp) {
        return timestamp == null ? null : new Date(timestamp.getTime());
    }

    private static void setTimestamp(final PreparedStatement statement, final int index, final Date value)
            throws SQLException {
        if (value == null) {
            statement.setTimestamp(index, null);
        } else {
            statement.setTimestamp(index, new Timestamp(value.getTime()));
        }
    }

    public static final class EmailAlreadyExistsException extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }

    public static final class UsernameAlreadyExistsException extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }

    public static final class LastAdministratorException extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }

    public static final class InvalidRoleTransitionException extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }

    private static User findUserById(final Connection connection, final UUID userId) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT " + COLUMNS + " FROM users WHERE id = ? FOR UPDATE")) {
            statement.setObject(1, userId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        }
    }

    private static int countAdministrators(final Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'")) {
            result.next();
            return result.getInt(1);
        }
    }

    private static String uniqueConstraint(final SQLException exception) {
        SQLException current = exception;
        while (current != null) {
            if (current instanceof PSQLException
                    && ((PSQLException) current).getServerErrorMessage() != null) {
                return ((PSQLException) current).getServerErrorMessage().getConstraint();
            }
            current = current.getNextException();
        }
        return null;
    }

    public static User createUser(final UUID id, final String username, final String firstName,
                                  final String lastName, final String email, final String phone,
                                  final AccountStatus userStatus) {
        return createUser(id, username, firstName, lastName, email, "XXXXXXXXXXX", phone,
                userStatus, Role.USER);
    }

    public static User createUser(final UUID id, final String username, final String firstName,
                                  final String lastName, final String email, final String password,
                                  final String phone, final AccountStatus userStatus, final Role role) {
        final User user = new User();
        user.setId(id);
        user.setUsername(username);
        user.setFirstName(firstName);
        user.setLastName(lastName);
        user.setEmail(email);
        user.setPassword(password);
        user.setPhone(phone);
        user.setUserStatus(userStatus);
        user.setRole(role == null ? Role.USER : role);
        return user;
    }
}
