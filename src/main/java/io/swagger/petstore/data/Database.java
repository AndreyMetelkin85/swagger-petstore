package io.swagger.petstore.data;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

/** Minimal JDBC connection factory configured through environment variables. */
public final class Database {
    private static final String DEFAULT_URL = "jdbc:postgresql://localhost:5432/petstore";
    private static final String DEFAULT_USER = "petstore";
    private static final String DEFAULT_PASSWORD = "petstore";
    private static volatile boolean migrated;

    private Database() {
    }

    public static Connection connect() throws SQLException {
        migrate();
        return DriverManager.getConnection(
                url(), user(), password());
    }

    private static void migrate() {
        if (migrated) {
            return;
        }
        synchronized (Database.class) {
            if (migrated) {
                return;
            }
            Flyway.configure()
                    .dataSource(url(), user(), password())
                    .baselineOnMigrate(true)
                    .baselineVersion(MigrationVersion.fromVersion("1"))
                    .load()
                    .migrate();
            migrated = true;
        }
    }

    public static boolean isHealthy() {
        try (Connection connection = connect();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT 1")) {
            return result.next() && result.getInt(1) == 1;
        } catch (SQLException exception) {
            return false;
        }
    }

    public static IllegalStateException failure(final String operation, final SQLException exception) {
        return new IllegalStateException("Database operation failed: " + operation, exception);
    }

    public static boolean isUniqueViolation(final SQLException exception) {
        SQLException current = exception;
        while (current != null) {
            if ("23505".equals(current.getSQLState())) {
                return true;
            }
            current = current.getNextException();
        }
        return false;
    }

    private static String environment(final String name, final String fallback) {
        final String value = System.getenv(name);
        return value == null || value.trim().isEmpty() ? fallback : value;
    }

    private static String url() {
        return environment("PETSTORE_DB_URL", DEFAULT_URL);
    }

    private static String user() {
        return environment("PETSTORE_DB_USER", DEFAULT_USER);
    }

    private static String password() {
        return environment("PETSTORE_DB_PASSWORD", DEFAULT_PASSWORD);
    }
}
