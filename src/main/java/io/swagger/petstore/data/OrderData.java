package io.swagger.petstore.data;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.petstore.model.DeliveryDetails;
import io.swagger.petstore.model.Order;
import io.swagger.petstore.model.OrderCreateRequest;
import io.swagger.petstore.model.OrderStatus;
import io.swagger.petstore.model.PaymentStatus;
import io.swagger.petstore.model.PetStatus;
import io.swagger.petstore.model.User;
import io.swagger.petstore.service.OrderException;

import javax.ws.rs.core.Response;
import java.io.IOException;
import java.math.BigDecimal;
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

/** PostgreSQL-backed order repository with transactional reservation and payment lifecycle. */
public class OrderData {
    public static final int PAYMENT_TIMEOUT_MINUTES = 15;
    static final String COLUMNS = "id, owner_user_id, pet_id, quantity, status, unit_price, "
            + "total_amount, currency, delivery_details, payment_status, payment_expires_at, "
            + "ship_date, complete, created_at";
    private static final ObjectMapper JSON = new ObjectMapper();

    public Order getOrderById(final UUID orderId) {
        if (orderId == null) {
            return null;
        }
        expireOverdueOrders();
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

    public UUID getOrderOwner(final UUID orderId) {
        if (orderId == null) {
            return null;
        }
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT owner_user_id FROM store_orders WHERE id = ?")) {
            statement.setObject(1, orderId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? (UUID) result.getObject(1) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("find order owner", exception);
        }
    }

    public List<Order> findOrdersForUser(final UUID userId) {
        return findOrders(" WHERE owner_user_id = ?", userId);
    }

    public List<Order> findAll() {
        return findOrders("", null);
    }

    private List<Order> findOrders(final String condition, final UUID userId) {
        expireOverdueOrders();
        final List<Order> orders = new ArrayList<>();
        final String sql = "SELECT " + COLUMNS + " FROM store_orders" + condition
                + " ORDER BY created_at, id";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            if (userId != null) {
                statement.setObject(1, userId);
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
        expireOverdueOrders();
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
        expireOverdueOrders();
        return exists("SELECT 1 FROM store_orders WHERE pet_id = ? "
                + "AND status IN ('placed', 'approved', 'shipped')", petId);
    }

    /** Locks the pet row so concurrent attempts cannot reserve the same animal. */
    public Order placeOrder(final OrderCreateRequest request, final User owner) {
        try (Connection connection = Database.connect()) {
            connection.setAutoCommit(false);
            try {
                expireExistingReservation(connection, request.getPetId());
                final LockedPet pet = lockPet(connection, request.getPetId());
                if (pet == null) {
                    throw new OrderException(Response.Status.NOT_FOUND, "PET_NOT_FOUND",
                            "Pet was not found");
                }
                if (pet.status != PetStatus.AVAILABLE || hasActiveOrder(connection, request.getPetId())) {
                    throw new OrderException(Response.Status.CONFLICT, "PET_NOT_AVAILABLE",
                            "Pet is not available for ordering");
                }

                final DeliveryDetails delivery = new DeliveryDetails(owner.getFirstName(),
                        owner.getLastName(), owner.getPhone(), owner.getAddress());
                final Order order = insertOrder(connection, request, owner.getId(), pet.price, delivery);
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

    /** Applies a validated state transition and updates the linked pet/payment in one transaction. */
    public Order transition(final UUID orderId, final OrderStatus target,
                            final UUID actorUserId, final boolean admin) {
        try (Connection connection = Database.connect()) {
            connection.setAutoCommit(false);
            try {
                final LockedOrder current = lockOrder(connection, orderId);
                if (current == null) {
                    throw new OrderException(Response.Status.NOT_FOUND, "ORDER_NOT_FOUND",
                            "Order was not found");
                }
                expireLockedOrderIfNeeded(connection, current.order);
                if (!admin && !current.ownerUserId.equals(actorUserId)) {
                    throw new OrderException(Response.Status.FORBIDDEN, "ORDER_ACCESS_DENIED",
                            "Users may modify only their own orders");
                }
                if (!current.order.getStatus().canTransitionTo(target)) {
                    throw new OrderException(Response.Status.CONFLICT, "INVALID_STATUS_TRANSITION",
                            "Order cannot transition from " + current.order.getStatus().getValue()
                                    + " to " + target.getValue());
                }
                if (target == OrderStatus.APPROVED
                        && current.order.getPaymentStatus() != PaymentStatus.PAID
                        && current.order.getPaymentStatus() != PaymentStatus.NOT_REQUIRED) {
                    throw new OrderException(Response.Status.CONFLICT, "ORDER_NOT_PAID",
                            "The order must be paid before approval");
                }

                final Date shipDate = target == OrderStatus.SHIPPED
                        ? new Date() : current.order.getShipDate();
                PaymentStatus paymentStatus = current.order.getPaymentStatus();
                if (target == OrderStatus.CANCELLED && paymentStatus == PaymentStatus.PAID) {
                    refundPayment(connection, orderId);
                    paymentStatus = PaymentStatus.REFUNDED;
                }
                updateOrderStatus(connection, orderId, target, shipDate, paymentStatus);
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
                current.order.setPaymentStatus(paymentStatus);
                return current.order;
            } catch (SQLException | RuntimeException exception) {
                rollback(connection, exception);
                throw exception;
            }
        } catch (SQLException exception) {
            throw Database.failure("transition order", exception);
        }
    }

    /** Expires all due unpaid reservations. Rows already handled by another worker are skipped. */
    public int expireOverdueOrders() {
        int expired = 0;
        try (Connection connection = Database.connect()) {
            connection.setAutoCommit(false);
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT " + COLUMNS + " FROM store_orders "
                            + "WHERE status = 'placed' AND payment_status = 'UNPAID' "
                            + "AND payment_expires_at <= CURRENT_TIMESTAMP "
                            + "FOR UPDATE SKIP LOCKED")) {
                try (ResultSet result = statement.executeQuery()) {
                    while (result.next()) {
                        final Order order = map(result);
                        expireLockedOrder(connection, order);
                        expired++;
                    }
                }
                connection.commit();
                return expired;
            } catch (SQLException | RuntimeException exception) {
                rollback(connection, exception);
                throw exception;
            }
        } catch (SQLException exception) {
            throw Database.failure("expire unpaid orders", exception);
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

    private static LockedPet lockPet(final Connection connection, final UUID petId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT status, price FROM pets WHERE id = ? FOR UPDATE")) {
            statement.setObject(1, petId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? new LockedPet(PetStatus.fromValue(result.getString("status")),
                        result.getBigDecimal("price")) : null;
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

    private static void expireExistingReservation(final Connection connection, final UUID petId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT " + COLUMNS + " FROM store_orders WHERE pet_id = ? "
                        + "AND status = 'placed' AND payment_status = 'UNPAID' "
                        + "AND payment_expires_at <= CURRENT_TIMESTAMP FOR UPDATE")) {
            statement.setObject(1, petId);
            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    expireLockedOrder(connection, map(result));
                }
            }
        }
    }

    private static Order insertOrder(final Connection connection, final OrderCreateRequest request,
                                     final UUID ownerUserId, final BigDecimal unitPrice,
                                     final DeliveryDetails delivery) throws SQLException {
        final BigDecimal total = unitPrice.multiply(BigDecimal.valueOf(request.getQuantity()));
        final String sql = "INSERT INTO store_orders "
                + "(pet_id, quantity, ship_date, status, complete, owner_user_id, created_at, "
                + "unit_price, total_amount, currency, delivery_details, payment_status, payment_expires_at) "
                + "VALUES (?, ?, NULL, 'placed', FALSE, ?, CURRENT_TIMESTAMP, ?, ?, 'RUB', "
                + "CAST(? AS jsonb), 'UNPAID', CURRENT_TIMESTAMP + INTERVAL '15 minutes') "
                + "RETURNING " + COLUMNS;
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, request.getPetId());
            statement.setInt(2, request.getQuantity());
            statement.setObject(3, ownerUserId);
            statement.setBigDecimal(4, unitPrice);
            statement.setBigDecimal(5, total);
            statement.setString(6, toJson(delivery));
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                return map(result);
            }
        }
    }

    static LockedOrder lockOrder(final Connection connection, final UUID orderId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT " + COLUMNS + " FROM store_orders WHERE id = ? FOR UPDATE")) {
            statement.setObject(1, orderId);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return null;
                }
                return new LockedOrder(map(result), (UUID) result.getObject("owner_user_id"));
            }
        }
    }

    private static void updateOrderStatus(final Connection connection, final UUID orderId,
                                          final OrderStatus target, final Date shipDate,
                                          final PaymentStatus paymentStatus) throws SQLException {
        final String sql = "UPDATE store_orders SET status = CAST(? AS order_status), complete = ?, "
                + "ship_date = ?, payment_status = CAST(? AS order_payment_status) WHERE id = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, target.getValue());
            statement.setBoolean(2, target.isComplete());
            statement.setTimestamp(3, shipDate == null ? null : new Timestamp(shipDate.getTime()));
            statement.setString(4, paymentStatus.getValue());
            statement.setObject(5, orderId);
            statement.executeUpdate();
        }
    }

    static void expireLockedOrderIfNeeded(final Connection connection, final Order order)
            throws SQLException {
        if (order.getStatus() == OrderStatus.PLACED
                && order.getPaymentStatus() == PaymentStatus.UNPAID
                && order.getPaymentExpiresAt() != null
                && !order.getPaymentExpiresAt().after(new Date())) {
            expireLockedOrder(connection, order);
        }
    }

    static void expireLockedOrder(final Connection connection, final Order order) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE store_orders SET status = 'expired', complete = TRUE, "
                        + "payment_status = 'EXPIRED' WHERE id = ?")) {
            statement.setObject(1, order.getId());
            statement.executeUpdate();
        }
        updatePetStatus(connection, order.getPetId(), PetStatus.AVAILABLE);
        order.setStatus(OrderStatus.EXPIRED);
        order.setComplete(true);
        order.setPaymentStatus(PaymentStatus.EXPIRED);
    }

    private static void refundPayment(final Connection connection, final UUID orderId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE payments SET status = 'REFUNDED', updated_at = CURRENT_TIMESTAMP "
                        + "WHERE order_id = ? AND status = 'SUCCEEDED'")) {
            statement.setObject(1, orderId);
            if (statement.executeUpdate() != 1) {
                throw new OrderException(Response.Status.CONFLICT, "PAYMENT_STATE_CONFLICT",
                        "The successful payment could not be refunded");
            }
        }
    }

    static void updatePetStatus(final Connection connection, final UUID petId,
                                final PetStatus status) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE pets SET status = CAST(? AS pet_status), version = version + 1 WHERE id = ?")) {
            statement.setString(1, status.getValue());
            statement.setObject(2, petId);
            statement.executeUpdate();
        }
    }

    static void rollback(final Connection connection, final Exception cause) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            cause.addSuppressed(rollbackFailure);
        }
    }

    static Order map(final ResultSet result) throws SQLException {
        final Order order = new Order();
        order.setId((UUID) result.getObject("id"));
        order.setPetId((UUID) result.getObject("pet_id"));
        order.setQuantity(result.getInt("quantity"));
        order.setShipDate(toDate(result.getTimestamp("ship_date")));
        order.setStatus(OrderStatus.fromValue(result.getString("status")));
        order.setComplete(result.getBoolean("complete"));
        order.setUserId((UUID) result.getObject("owner_user_id"));
        order.setCreatedAt(toDate(result.getTimestamp("created_at")));
        order.setUnitPrice(result.getBigDecimal("unit_price"));
        order.setTotalAmount(result.getBigDecimal("total_amount"));
        order.setCurrency(result.getString("currency"));
        order.setDeliveryDetails(fromJson(result.getString("delivery_details")));
        order.setPaymentStatus(PaymentStatus.fromValue(result.getString("payment_status")));
        order.setPaymentExpiresAt(toDate(result.getTimestamp("payment_expires_at")));
        return order;
    }

    private static String toJson(final DeliveryDetails value) {
        try {
            return JSON.writeValueAsString(value);
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot serialize delivery details", exception);
        }
    }

    private static DeliveryDetails fromJson(final String value) {
        if (value == null) {
            return null;
        }
        try {
            return JSON.readValue(value, DeliveryDetails.class);
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot deserialize delivery details", exception);
        }
    }

    private static Date toDate(final Timestamp value) {
        return value == null ? null : new Date(value.getTime());
    }

    static final class LockedOrder {
        private final Order order;
        private final UUID ownerUserId;

        private LockedOrder(final Order order, final UUID ownerUserId) {
            this.order = order;
            this.ownerUserId = ownerUserId;
        }

        Order getOrder() {
            return order;
        }

        UUID getOwnerUserId() {
            return ownerUserId;
        }
    }

    private static final class LockedPet {
        private final PetStatus status;
        private final BigDecimal price;

        private LockedPet(final PetStatus status, final BigDecimal price) {
            this.status = status;
            this.price = price;
        }
    }
}
