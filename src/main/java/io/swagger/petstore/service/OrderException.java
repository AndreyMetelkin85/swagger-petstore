package io.swagger.petstore.service;

import javax.ws.rs.core.Response;

/** Expected order-domain failure mapped by the controller to the public error contract. */
public class OrderException extends RuntimeException {
    private final Response.Status status;
    private final String code;

    public OrderException(final Response.Status status, final String code, final String message) {
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
