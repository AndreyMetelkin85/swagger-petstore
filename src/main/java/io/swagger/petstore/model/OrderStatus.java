package io.swagger.petstore.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

/** Persisted order states and their allowed forward transitions. */
public enum OrderStatus {
    PLACED("placed"),
    APPROVED("approved"),
    SHIPPED("shipped"),
    DELIVERED("delivered"),
    CANCELLED("cancelled"),
    EXPIRED("expired");

    private final String value;

    OrderStatus(final String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    @JsonCreator
    public static OrderStatus fromValue(final String value) {
        if (value != null) {
            for (OrderStatus status : values()) {
                if (status.value.equalsIgnoreCase(value)) {
                    return status;
                }
            }
        }
        throw new IllegalArgumentException("Unknown order status: " + value);
    }

    public boolean canTransitionTo(final OrderStatus target) {
        if (this == PLACED) {
            return target == APPROVED || target == CANCELLED;
        }
        if (this == APPROVED) {
            return target == SHIPPED || target == CANCELLED;
        }
        return this == SHIPPED && target == DELIVERED;
    }

    public boolean isActive() {
        return this == PLACED || this == APPROVED || this == SHIPPED;
    }

    public boolean isComplete() {
        return this == DELIVERED || this == CANCELLED || this == EXPIRED;
    }

    @Override
    public String toString() {
        return value;
    }
}
