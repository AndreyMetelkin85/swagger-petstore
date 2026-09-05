package io.swagger.petstore.data;

import io.swagger.petstore.model.Order;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** PostgreSQL-backed order repository with persisted ownership metadata. */
public class OrderData {
    private static final String COLUMNS =
            "id, pet_id, quantity, ship_date, status, complete, owner_username";

    public Order getOrderById(final UUID orderId) {
        if (orderId == null) {
            return null;
        }
        final String sql = "SELECT " + COLUMNS + " FROM store_orders WHERE id = ?";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, orderId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("find order", exception);
        }
    }

    public String getOrderOwner(final UUID orderId) {
        if (orderId == null) {
            return null;
        }
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT owner_username FROM store_orders WHERE id = ?")) {
            statement.setObject(1, orderId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? result.getString(1) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("find order owner", exception);
        }
    }

    public List<Order> findOrdersForUser(final String username) {
        final List<Order> orders = new ArrayList<>();
        final String sql = "SELECT " + COLUMNS
                + " FROM store_orders WHERE owner_username = ? ORDER BY id";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, username);
            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    orders.add(map(result));
                }
            }
            return orders;
        } catch (SQLException exception) {
            throw Database.failure("list orders", exception);
        }
    }

    public Map<String, Integer> getCountByStatus() {
        final Map<String, Integer> totals = new LinkedHashMap<>();
        final String sql = "SELECT status, COALESCE(SUM(quantity), 0) AS total "
                + "FROM store_orders GROUP BY status ORDER BY status";
        try (Connection connection = Database.connect();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(sql)) {
            while (result.next()) {
                totals.put(result.getString("status"), result.getInt("total"));
            }
            return totals;
        } catch (SQLException exception) {
            throw Database.failure("calculate inventory", exception);
        }
    }

    public Order addOrder(final Order order, final String owner) {
        if (order.getShipDate() == null) {
            order.setShipDate(new Date());
        }
        if (order.getStatus() == null) {
            order.setStatus("placed");
        }
        if (order.isComplete() == null) {
            order.setComplete(false);
        }
        final boolean suppliedId = order.getId() != null;
        final String sql = suppliedId
                ? "INSERT INTO store_orders (id, pet_id, quantity, ship_date, status, complete, owner_username) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET "
                + "pet_id = EXCLUDED.pet_id, quantity = EXCLUDED.quantity, ship_date = EXCLUDED.ship_date, "
                + "status = EXCLUDED.status, complete = EXCLUDED.complete, "
                + "owner_username = EXCLUDED.owner_username RETURNING id"
                : "INSERT INTO store_orders (pet_id, quantity, ship_date, status, complete, owner_username) "
                + "VALUES (?, ?, ?, ?, ?, ?) RETURNING id";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            int index = 1;
            if (suppliedId) {
                statement.setObject(index++, order.getId());
            }
            statement.setObject(index++, order.getPetId());
            statement.setInt(index++, order.getQuantity());
            statement.setTimestamp(index++, new Timestamp(order.getShipDate().getTime()));
            statement.setString(index++, order.getStatus());
            statement.setBoolean(index++, order.isComplete());
            statement.setString(index, owner);
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                order.setId((UUID) result.getObject(1));
            }
            return order;
        } catch (SQLException exception) {
            throw Database.failure("create order", exception);
        }
    }

    public void addOrder(final Order order) {
        addOrder(order, "admin");
    }

    public boolean deleteOrderById(final UUID orderId) {
        if (orderId == null) {
            return false;
        }
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(
                     "DELETE FROM store_orders WHERE id = ?")) {
            statement.setObject(1, orderId);
            return statement.executeUpdate() > 0;
        } catch (SQLException exception) {
            throw Database.failure("delete order", exception);
        }
    }

    private static Order map(final ResultSet result) throws SQLException {
        final Timestamp shipDate = result.getTimestamp("ship_date");
        return createOrder((UUID) result.getObject("id"), (UUID) result.getObject("pet_id"),
                result.getInt("quantity"),
                shipDate == null ? null : new Date(shipDate.getTime()),
                result.getString("status"), result.getBoolean("complete"));
    }

    public static Order createOrder(final UUID id, final UUID petId, final int quantity,
                                    final Date shipDate, final String status, final boolean complete) {
        final Order order = new Order();
        order.setId(id);
        order.setPetId(petId);
        order.setComplete(complete);
        order.setQuantity(quantity);
        order.setShipDate(shipDate);
        order.setStatus(status);
        return order;
    }
}
