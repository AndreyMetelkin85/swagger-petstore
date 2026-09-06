package io.swagger.petstore.data;

import io.swagger.petstore.model.Order;
import io.swagger.petstore.model.OrderStatus;
import io.swagger.petstore.model.Payment;
import io.swagger.petstore.model.PaymentAttemptStatus;
import io.swagger.petstore.model.PaymentRequest;
import io.swagger.petstore.model.PaymentStatus;
import io.swagger.petstore.model.User;
import io.swagger.petstore.service.PaymentException;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

/** PostgreSQL-backed local test-card payment simulator. */
public class PaymentData {
    private static final String SUCCESS_CARD = "4242424242424242";
    private static final String DECLINED_CARD = "4000000000000002";
    private static final String INSUFFICIENT_FUNDS_CARD = "4000000000009995";
    private static final String COLUMNS = "id, order_id, amount, currency, status, card_brand, "
            + "card_last4, failure_code, created_at, updated_at";

    public PaymentResult createPayment(final UUID orderId, final UUID idempotencyKey,
                                       final PaymentRequest request, final User actor,
                                       final boolean admin) {
        final String requestHash = requestHash(orderId, request);
        try (Connection connection = Database.connect()) {
            connection.setAutoCommit(false);
            try {
                lockIdempotencyKey(connection, idempotencyKey);
                final OrderData.LockedOrder locked = OrderData.lockOrder(connection, orderId);
                if (locked == null) {
                    throw new PaymentException(404, "ORDER_NOT_FOUND", "Order was not found");
                }
                if (!admin && !actor.getId().equals(locked.getOwnerUserId())) {
                    throw new PaymentException(403, "ORDER_ACCESS_DENIED",
                            "Users may access only payments for their own orders");
                }

                final ExistingPayment existing = findByIdempotencyKey(connection, idempotencyKey);
                if (existing != null) {
                    if (!existing.payment.getOrderId().equals(orderId)
                            || !existing.requestHash.equals(requestHash)) {
                        throw new PaymentException(409, "IDEMPOTENCY_KEY_REUSED",
                                "Idempotency-Key was already used with another request");
                    }
                    connection.commit();
                    throwIfDeclined(existing.payment);
                    return new PaymentResult(existing.payment, true);
                }

                final Order order = locked.getOrder();
                OrderData.expireLockedOrderIfNeeded(connection, order);
                if (order.getStatus() == OrderStatus.EXPIRED
                        || order.getPaymentStatus() == PaymentStatus.EXPIRED) {
                    connection.commit();
                    throw new PaymentException(410, "ORDER_PAYMENT_EXPIRED",
                            "The payment period for this order has expired");
                }
                if (order.getPaymentStatus() == PaymentStatus.PAID
                        || order.getPaymentStatus() == PaymentStatus.REFUNDED) {
                    throw new PaymentException(409, "ORDER_ALREADY_PAID",
                            "The order already has a successful payment");
                }
                if (order.getPaymentStatus() == PaymentStatus.NOT_REQUIRED
                        || order.getStatus() != OrderStatus.PLACED) {
                    throw new PaymentException(409, "ORDER_NOT_PAYABLE",
                            "The order cannot be paid in its current state");
                }

                final String failureCode = failureCode(request.getCardNumber());
                final PaymentAttemptStatus status = failureCode == null
                        ? PaymentAttemptStatus.SUCCEEDED : PaymentAttemptStatus.DECLINED;
                final Payment payment = insertPayment(connection, order, idempotencyKey,
                        requestHash, request.getCardNumber(), status, failureCode);
                if (status == PaymentAttemptStatus.SUCCEEDED) {
                    markOrderPaid(connection, orderId);
                }
                connection.commit();
                throwIfDeclined(payment);
                return new PaymentResult(payment, false);
            } catch (SQLException | RuntimeException exception) {
                OrderData.rollback(connection, exception);
                throw exception;
            }
        } catch (SQLException exception) {
            throw Database.failure("create payment", exception);
        }
    }

    public List<Payment> findPayments(final UUID orderId, final User actor, final boolean admin) {
        assertOrderAccess(orderId, actor, admin);
        final List<Payment> payments = new ArrayList<>();
        final String sql = "SELECT " + COLUMNS + " FROM payments WHERE order_id = ? "
                + "ORDER BY created_at, id";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, orderId);
            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    payments.add(map(result));
                }
            }
            return payments;
        } catch (SQLException exception) {
            throw Database.failure("list payments", exception);
        }
    }

    public Payment getPayment(final UUID orderId, final UUID paymentId,
                              final User actor, final boolean admin) {
        assertOrderAccess(orderId, actor, admin);
        final String sql = "SELECT " + COLUMNS + " FROM payments WHERE order_id = ? AND id = ?";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, orderId);
            statement.setObject(2, paymentId);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new PaymentException(404, "PAYMENT_NOT_FOUND", "Payment was not found");
                }
                return map(result);
            }
        } catch (SQLException exception) {
            throw Database.failure("find payment", exception);
        }
    }

    private static void assertOrderAccess(final UUID orderId, final User actor, final boolean admin) {
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT owner_user_id FROM store_orders WHERE id = ?")) {
            statement.setObject(1, orderId);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new PaymentException(404, "ORDER_NOT_FOUND", "Order was not found");
                }
                final UUID owner = (UUID) result.getObject(1);
                if (!admin && !actor.getId().equals(owner)) {
                    throw new PaymentException(403, "ORDER_ACCESS_DENIED",
                            "Users may access only payments for their own orders");
                }
            }
        } catch (SQLException exception) {
            throw Database.failure("authorize payment access", exception);
        }
    }

    private static void lockIdempotencyKey(final Connection connection, final UUID key)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT pg_advisory_xact_lock(?)")) {
            statement.setLong(1, key.getMostSignificantBits() ^ key.getLeastSignificantBits());
            statement.executeQuery().close();
        }
    }

    private static ExistingPayment findByIdempotencyKey(final Connection connection, final UUID key)
            throws SQLException {
        final String sql = "SELECT " + COLUMNS + ", request_hash FROM payments "
                + "WHERE idempotency_key = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, key);
            try (ResultSet result = statement.executeQuery()) {
                return result.next()
                        ? new ExistingPayment(map(result), result.getString("request_hash")) : null;
            }
        }
    }

    private static Payment insertPayment(final Connection connection, final Order order,
                                         final UUID key, final String requestHash,
                                         final String cardNumber,
                                         final PaymentAttemptStatus status,
                                         final String failureCode) throws SQLException {
        final String sql = "INSERT INTO payments (order_id, idempotency_key, request_hash, amount, "
                + "currency, status, card_brand, card_last4, failure_code) "
                + "VALUES (?, ?, ?, ?, 'RUB', CAST(? AS payment_attempt_status), ?, ?, ?) "
                + "RETURNING " + COLUMNS;
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, order.getId());
            statement.setObject(2, key);
            statement.setString(3, requestHash);
            statement.setBigDecimal(4, order.getTotalAmount());
            statement.setString(5, status.name());
            statement.setString(6, cardBrand(cardNumber));
            statement.setString(7, cardNumber.substring(cardNumber.length() - 4));
            statement.setString(8, failureCode);
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                return map(result);
            }
        }
    }

    private static void markOrderPaid(final Connection connection, final UUID orderId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE store_orders SET payment_status = 'PAID' WHERE id = ? "
                        + "AND status = 'placed' AND payment_status = 'UNPAID'")) {
            statement.setObject(1, orderId);
            if (statement.executeUpdate() != 1) {
                throw new PaymentException(409, "PAYMENT_STATE_CONFLICT",
                        "The order payment state changed concurrently");
            }
        }
    }

    private static String failureCode(final String cardNumber) {
        if (DECLINED_CARD.equals(cardNumber)) {
            return "PAYMENT_DECLINED";
        }
        if (INSUFFICIENT_FUNDS_CARD.equals(cardNumber)) {
            return "INSUFFICIENT_FUNDS";
        }
        return SUCCESS_CARD.equals(cardNumber) ? null : "PAYMENT_DECLINED";
    }

    private static String cardBrand(final String cardNumber) {
        return cardNumber.startsWith("4") ? "VISA" : "UNKNOWN";
    }

    private static void throwIfDeclined(final Payment payment) {
        if (payment.getStatus() != PaymentAttemptStatus.DECLINED) {
            return;
        }
        final String code = payment.getFailureCode();
        final String message = "INSUFFICIENT_FUNDS".equals(code)
                ? "The test card has insufficient funds" : "The test card payment was declined";
        throw new PaymentException(402, code, message);
    }

    private static Payment map(final ResultSet result) throws SQLException {
        final Payment payment = new Payment();
        payment.setId((UUID) result.getObject("id"));
        payment.setOrderId((UUID) result.getObject("order_id"));
        payment.setAmount(result.getBigDecimal("amount"));
        payment.setCurrency(result.getString("currency"));
        payment.setStatus(PaymentAttemptStatus.valueOf(result.getString("status")));
        payment.setCardBrand(result.getString("card_brand"));
        payment.setCardLast4(result.getString("card_last4"));
        payment.setFailureCode(result.getString("failure_code"));
        payment.setCreatedAt(toDate(result.getTimestamp("created_at")));
        payment.setUpdatedAt(toDate(result.getTimestamp("updated_at")));
        return payment;
    }

    private static String requestHash(final UUID orderId, final PaymentRequest request) {
        final String canonical = orderId + "|" + request.getCardNumber() + "|"
                + request.getExpiryMonth() + "|" + request.getExpiryYear() + "|"
                + request.getCvv() + "|" + request.getCardholderName().trim().toUpperCase(Locale.ROOT);
        try {
            final byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.getBytes(StandardCharsets.UTF_8));
            final StringBuilder result = new StringBuilder(digest.length * 2);
            for (byte value : digest) {
                result.append(String.format("%02x", value & 0xff));
            }
            return result.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is not available", exception);
        }
    }

    private static Date toDate(final Timestamp value) {
        return value == null ? null : new Date(value.getTime());
    }

    private static final class ExistingPayment {
        private final Payment payment;
        private final String requestHash;

        private ExistingPayment(final Payment payment, final String requestHash) {
            this.payment = payment;
            this.requestHash = requestHash;
        }
    }

    public static final class PaymentResult {
        private final Payment payment;
        private final boolean replayed;

        private PaymentResult(final Payment payment, final boolean replayed) {
            this.payment = payment;
            this.replayed = replayed;
        }

        public Payment getPayment() {
            return payment;
        }

        public boolean isReplayed() {
            return replayed;
        }
    }
}
