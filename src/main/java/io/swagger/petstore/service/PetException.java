package io.swagger.petstore.service;

import javax.ws.rs.core.Response;

/** Expected pet-domain failure mapped by the controller to the public error contract. */
public class PetException extends RuntimeException {
    private final Response.Status status;
    private final String code;

    public PetException(final Response.Status status, final String code, final String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public Response.Status getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }
}
