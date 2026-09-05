package io.swagger.petstore.data;

import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;
import io.swagger.petstore.model.UserUpdateRequest;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

/** PostgreSQL-backed user repository for local API testing. */
public class UserData {
    private static final String COLUMNS =
            "id, username, first_name, last_name, email, password, phone, user_status, role";

    public User findUserByName(final String username) {
        if (username == null) {
            return null;
        }
        final String sql = "SELECT " + COLUMNS + " FROM users WHERE username = ?";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, username);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("find user", exception);
        }
    }

    public User authenticate(final String username, final String password) {
        final User user = findUserByName(username);
        if (user == null || password == null || !password.equals(user.getPassword())) {
            return null;
        }
        return user;
    }

    public boolean addUserIfAbsent(final User user) {
        if (user == null || user.getUsername() == null) {
            return false;
        }
        if (user.getRole() == null) {
            user.setRole(Role.USER);
        }
        final boolean suppliedId = user.getId() > 0;
        final String sql = suppliedId
                ? "INSERT INTO users (id, username, first_name, last_name, email, password, phone, user_status, role) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id"
                : "INSERT INTO users (username, first_name, last_name, email, password, phone, user_status, role) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            int index = 1;
            if (suppliedId) {
                statement.setLong(index++, user.getId());
            }
            bindUser(statement, index, user);
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                user.setId(result.getLong(1));
            }
            return true;
        } catch (SQLException exception) {
            if (Database.isUniqueViolation(exception)) {
                return false;
            }
            throw Database.failure("create user", exception);
        }
    }

    /** Legacy upsert behaviour retained for the original endpoints. */
    public void addUser(final User user) {
        if (user == null || user.getUsername() == null) {
            return;
        }
        if (user.getRole() == null) {
            user.setRole(Role.USER);
        }
        if (findUserByName(user.getUsername()) == null) {
            addUserIfAbsent(user);
            return;
        }
        final String sql = "UPDATE users SET first_name = ?, last_name = ?, email = ?, password = ?, "
                + "phone = ?, user_status = ?, role = ? WHERE username = ?";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, user.getFirstName());
            statement.setString(2, user.getLastName());
            statement.setString(3, user.getEmail());
            statement.setString(4, user.getPassword());
            statement.setString(5, user.getPhone());
            statement.setInt(6, user.getUserStatus());
            statement.setString(7, user.getRole().name());
            statement.setString(8, user.getUsername());
            statement.executeUpdate();
        } catch (SQLException exception) {
            throw Database.failure("upsert user", exception);
        }
    }

    public User updateUser(final String username, final UserUpdateRequest update) {
        if (username == null || update == null) {
            return null;
        }
        final String sql = "UPDATE users SET "
                + "first_name = COALESCE(?, first_name), last_name = COALESCE(?, last_name), "
                + "email = COALESCE(?, email), password = COALESCE(?, password), "
                + "phone = COALESCE(?, phone) WHERE username = ? RETURNING " + COLUMNS;
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, update.getFirstName());
            statement.setString(2, update.getLastName());
            statement.setString(3, update.getEmail());
            statement.setString(4, update.getPassword());
            statement.setString(5, update.getPhone());
            statement.setString(6, username);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("update user", exception);
        }
    }

    public void deleteUser(final String username) {
        if (username == null) {
            return;
        }
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(
                     "DELETE FROM users WHERE username = ?")) {
            statement.setString(1, username);
            statement.executeUpdate();
        } catch (SQLException exception) {
            throw Database.failure("delete user", exception);
        }
    }

    public List<User> findAll() {
        final List<User> users = new ArrayList<>();
        try (Connection connection = Database.connect();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(
                     "SELECT " + COLUMNS + " FROM users ORDER BY id")) {
            while (result.next()) {
                users.add(map(result));
            }
            return users;
        } catch (SQLException exception) {
            throw Database.failure("list users", exception);
        }
    }

    private static void bindUser(final PreparedStatement statement, final int start,
                                 final User user) throws SQLException {
        int index = start;
        statement.setString(index++, user.getUsername());
        statement.setString(index++, user.getFirstName());
        statement.setString(index++, user.getLastName());
        statement.setString(index++, user.getEmail());
        statement.setString(index++, user.getPassword());
        statement.setString(index++, user.getPhone());
        statement.setInt(index++, user.getUserStatus());
        statement.setString(index, user.getRole().name());
    }

    private static User map(final ResultSet result) throws SQLException {
        return createUser(result.getLong("id"), result.getString("username"),
                result.getString("first_name"), result.getString("last_name"),
                result.getString("email"), result.getString("password"),
                result.getString("phone"), result.getInt("user_status"),
                Role.valueOf(result.getString("role")));
    }

    public static User createUser(final long id, final String username, final String firstName,
                                  final String lastName, final String email, final String phone,
                                  final int userStatus) {
        return createUser(id, username, firstName, lastName, email, "XXXXXXXXXXX", phone,
                userStatus, Role.USER);
    }

    public static User createUser(final long id, final String username, final String firstName,
                                  final String lastName, final String email, final String password,
                                  final String phone, final int userStatus, final Role role) {
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
