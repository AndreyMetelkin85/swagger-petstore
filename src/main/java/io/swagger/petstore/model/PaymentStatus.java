package io.swagger.petstore.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

/** Payment state stored on an order. */
public enum PaymentStatus {
    NOT_REQUIRED,
    UNPAID,
    PAID,
    REFUNDED,
    EXPIRED;

    @JsonValue
    public String getValue() {
        return name();
    }

    @JsonCreator
    public static PaymentStatus fromValue(final String value) {
        return value == null ? null : valueOf(value.toUpperCase());
    }
}
