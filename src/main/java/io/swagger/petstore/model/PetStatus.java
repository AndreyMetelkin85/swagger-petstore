package io.swagger.petstore.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

/** Public catalog states for an individual pet. */
public enum PetStatus {
    AVAILABLE("available"),
    PENDING("pending"),
    RESERVED("reserved"),
    SOLD("sold");

    private final String value;

    PetStatus(final String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    @JsonCreator
    public static PetStatus fromValue(final String value) {
        if (value != null) {
            for (PetStatus status : values()) {
                if (status.value.equalsIgnoreCase(value)) {
                    return status;
                }
            }
        }
        throw new IllegalArgumentException("Unknown pet status: " + value);
    }

    @Override
    public String toString() {
        return value;
    }
}
