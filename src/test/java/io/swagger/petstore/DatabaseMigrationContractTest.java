package io.swagger.petstore;

import org.junit.Test;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class DatabaseMigrationContractTest {
    private static final String MIGRATION =
            "/db/migration/V7__reorder_database_columns.sql";

    @Test
    public void v7DefinesTheRequiredPhysicalColumnOrder() throws IOException {
        final String sql = readMigration();

        assertEquals(List.of(
                "id", "username", "first_name", "last_name", "email", "password",
                "role", "user_status", "phone", "address_city", "address_street",
                "address_house", "address_apartment", "address_postal_code",
                "confirmation_code_hash", "confirmation_expires_at", "reset_code_hash",
                "reset_expires_at", "reset_used_at", "token_version", "confirmed_at"
        ), columnsOf(sql, "users_v7"));
        assertEquals(List.of(
                "id", "name", "status", "category_json", "photo_urls_json",
                "tags_json", "price", "version"
        ), columnsOf(sql, "pets_v7"));
        assertEquals(List.of(
                "id", "owner_user_id", "pet_id", "quantity", "status", "unit_price",
                "total_amount", "currency", "delivery_details", "payment_status",
                "payment_expires_at", "ship_date", "complete", "created_at"
        ), columnsOf(sql, "store_orders_v7"));
        assertEquals(List.of(
                "id", "order_id", "status", "idempotency_key", "request_hash", "amount",
                "currency", "card_brand", "card_last4", "failure_code", "created_at",
                "updated_at"
        ), columnsOf(sql, "payments_v7"));
    }

    @Test
    public void v7PreservesTheLegacyPetForeignKeyValidationState() throws IOException {
        final String sql = readMigration();

        assertTrue(sql.contains("ADD CONSTRAINT fk_store_orders_pet"));
        assertTrue(sql.contains(
                "FOREIGN KEY (pet_id) REFERENCES pets(id) ON DELETE RESTRICT NOT VALID"));
    }

    private static List<String> columnsOf(final String sql, final String table) {
        final String marker = "CREATE TABLE " + table + " (";
        final int start = sql.indexOf(marker);
        final int end = sql.indexOf("\n);", start);
        assertTrue("Missing CREATE TABLE for " + table, start >= 0 && end > start);
        final String body = sql.substring(start + marker.length(), end);
        return Arrays.stream(body.split(",\\R"))
                .map(String::trim)
                .map(line -> line.split("\\s+", 2)[0])
                .collect(Collectors.toList());
    }

    private static String readMigration() throws IOException {
        try (InputStream input = DatabaseMigrationContractTest.class.getResourceAsStream(MIGRATION)) {
            return new String(Objects.requireNonNull(input, "Missing " + MIGRATION).readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
