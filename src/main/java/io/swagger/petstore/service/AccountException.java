package io.swagger.petstore.service;

import javax.ws.rs.core.Response;

public class AccountException extends RuntimeException {
    private final Response.Status status;
    private final String code;

    public AccountException(Response.Status status, String code, String message) {
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
