package io.swagger.petstore.data;

import io.swagger.petstore.model.Order;
import io.swagger.petstore.model.OrderCreateRequest;
import io.swagger.petstore.model.OrderStatus;
import io.swagger.petstore.model.PetStatus;
import io.swagger.petstore.service.OrderException;

import javax.ws.rs.core.Response;
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

/** PostgreSQL-backed order repository with transactional pet reservation. */
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
        return findOrders(" WHERE owner_username = ?", username);
    }

    public List<Order> findAll() {
        return findOrders("", null);
    }

    private List<Order> findOrders(final String condition, final String username) {
        final List<Order> orders = new ArrayList<>();
        final String sql = "SELECT " + COLUMNS + " FROM store_orders" + condition + " ORDER BY id";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            if (username != null) {
                statement.setString(1, username);
            }
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

    public boolean hasOrdersForPet(final UUID petId) {
        return exists("SELECT 1 FROM store_orders WHERE pet_id = ?", petId);
    }

    public boolean hasActiveOrderForPet(final UUID petId) {
        return exists("SELECT 1 FROM store_orders WHERE pet_id = ? "
                + "AND status IN ('placed', 'approved', 'shipped')", petId);
    }

    /** Locks the pet row so concurrent attempts cannot reserve the same animal. */
    public Order placeOrder(final OrderCreateRequest request, final String owner) {
        try (Connection connection = Database.connect()) {
            connection.setAutoCommit(false);
            try {
                final PetStatus petStatus = lockPetStatus(connection, request.getPetId());
                if (petStatus == null) {
                    throw new OrderException(Response.Status.NOT_FOUND, "PET_NOT_FOUND",
                            "Pet was not found");
                }
                if (petStatus != PetStatus.AVAILABLE || hasActiveOrder(connection, request.getPetId())) {
                    throw new OrderException(Response.Status.CONFLICT, "PET_NOT_AVAILABLE",
                            "Pet is not available for ordering");
                }

                final Order order = insertOrder(connection, request, owner);
                updatePetStatus(connection, request.getPetId(), PetStatus.RESERVED);
                connection.commit();
                return order;
            } catch (SQLException | RuntimeException exception) {
                rollback(connection, exception);
                throw exception;
            }
        } catch (SQLException exception) {
            throw Database.failure("place order", exception);
        }
    }

    /** Applies a validated state transition and updates the linked pet in one transaction. */
    public Order transition(final UUID orderId, final OrderStatus target,
                            final String actorUsername, final boolean admin) {
        try (Connection connection = Database.connect()) {
            connection.setAutoCommit(false);
            try {
                final LockedOrder current = lockOrder(connection, orderId);
                if (current == null) {
                    throw new OrderException(Response.Status.NOT_FOUND, "ORDER_NOT_FOUND",
                            "Order was not found");
                }
                if (!admin && !current.owner.equals(actorUsername)) {
                    throw new OrderException(Response.Status.FORBIDDEN, "ORDER_ACCESS_DENIED",
                            "Users may modify only their own orders");
                }
                if (!current.order.getStatus().canTransitionTo(target)) {
                    throw new OrderException(Response.Status.CONFLICT, "INVALID_STATUS_TRANSITION",
                            "Order cannot transition from " + current.order.getStatus().getValue()
                                    + " to " + target.getValue());
                }

                final Date shipDate = target == OrderStatus.SHIPPED
                        ? new Date() : current.order.getShipDate();
                updateOrderStatus(connection, orderId, target, shipDate);
                if (target == OrderStatus.CANCELLED) {
                    if (!hasActiveOrder(connection, current.order.getPetId())) {
                        updatePetStatus(connection, current.order.getPetId(), PetStatus.AVAILABLE);
                    }
                } else if (target == OrderStatus.DELIVERED) {
                    updatePetStatus(connection, current.order.getPetId(), PetStatus.SOLD);
                }
                connection.commit();

                current.order.setStatus(target);
                current.order.setComplete(target.isComplete());
                current.order.setShipDate(shipDate);
                return current.order;
            } catch (SQLException | RuntimeException exception) {
                rollback(connection, exception);
                throw exception;
            }
        } catch (SQLException exception) {
            throw Database.failure("transition order", exception);
        }
    }

    private boolean exists(final String sql, final UUID petId) {
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, petId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next();
            }
        } catch (SQLException exception) {
            throw Database.failure("check pet orders", exception);
        }
    }

    private static PetStatus lockPetStatus(final Connection connection, final UUID petId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT status FROM pets WHERE id = ? FOR UPDATE")) {
            statement.setObject(1, petId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? PetStatus.fromValue(result.getString(1)) : null;
            }
        }
    }

    private static boolean hasActiveOrder(final Connection connection, final UUID petId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT 1 FROM store_orders WHERE pet_id = ? "
                        + "AND status IN ('placed', 'approved', 'shipped') LIMIT 1")) {
            statement.setObject(1, petId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next();
            }
        }
    }

    private static Order insertOrder(final Connection connection, final OrderCreateRequest request,
                                     final String owner) throws SQLException {
        final String sql = "INSERT INTO store_orders "
                + "(pet_id, quantity, ship_date, status, complete, owner_username) "
                + "VALUES (?, ?, NULL, CAST(? AS order_status), ?, ?) RETURNING id";
        final Order order = createOrder(null, request.getPetId(), request.getQuantity(), null,
                OrderStatus.PLACED, false);
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, request.getPetId());
            statement.setInt(2, request.getQuantity());
            statement.setString(3, OrderStatus.PLACED.getValue());
            statement.setBoolean(4, false);
            statement.setString(5, owner);
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                order.setId((UUID) result.getObject(1));
            }
            return order;
        }
    }

    private static LockedOrder lockOrder(final Connection connection, final UUID orderId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT " + COLUMNS + " FROM store_orders WHERE id = ? FOR UPDATE")) {
            statement.setObject(1, orderId);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return null;
                }
                return new LockedOrder(map(result), result.getString("owner_username"));
            }
        }
    }

    private static void updateOrderStatus(final Connection connection, final UUID orderId,
                                          final OrderStatus target, final Date shipDate)
            throws SQLException {
        final String sql = "UPDATE store_orders SET status = CAST(? AS order_status), complete = ?, "
                + "ship_date = ? WHERE id = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, target.getValue());
            statement.setBoolean(2, target.isComplete());
            statement.setTimestamp(3, shipDate == null ? null : new Timestamp(shipDate.getTime()));
            statement.setObject(4, orderId);
            statement.executeUpdate();
        }
    }

    private static void updatePetStatus(final Connection connection, final UUID petId,
                                        final PetStatus status) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE pets SET status = CAST(? AS pet_status), version = version + 1 WHERE id = ?")) {
            statement.setString(1, status.getValue());
            statement.setObject(2, petId);
            statement.executeUpdate();
        }
    }

    private static void rollback(final Connection connection, final Exception cause) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            cause.addSuppressed(rollbackFailure);
        }
    }

    private static Order map(final ResultSet result) throws SQLException {
        final Timestamp shipDate = result.getTimestamp("ship_date");
        return createOrder((UUID) result.getObject("id"), (UUID) result.getObject("pet_id"),
                result.getInt("quantity"), shipDate == null ? null : new Date(shipDate.getTime()),
                OrderStatus.fromValue(result.getString("status")), result.getBoolean("complete"));
    }

    public static Order createOrder(final UUID id, final UUID petId, final int quantity,
                                    final Date shipDate, final OrderStatus status,
                                    final boolean complete) {
        final Order order = new Order();
        order.setId(id);
        order.setPetId(petId);
        order.setComplete(complete);
        order.setQuantity(quantity);
        order.setShipDate(shipDate);
        order.setStatus(status);
        return order;
    }

    private static final class LockedOrder {
        private final Order order;
        private final String owner;

        private LockedOrder(final Order order, final String owner) {
            this.order = order;
            this.owner = owner;
        }
    }
}
