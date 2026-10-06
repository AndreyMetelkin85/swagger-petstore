package io.swagger.petstore.service;

import io.swagger.petstore.model.ErrorDetail;
import javax.ws.rs.core.Response;
import java.util.Collections;
import java.util.List;

public class AccountException extends RuntimeException {
    private final Response.Status status;
    private final String code;
    private final List<ErrorDetail> details;

    public AccountException(Response.Status status, String code, String message) {
        this(status, code, message, Collections.emptyList());
    }

    public AccountException(Response.Status status, String code, String message, List<ErrorDetail> details) {
        super(message);
        this.status = status;
        this.code = code;
        this.details = List.copyOf(details);
    }

    public Response.Status getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }

    public List<ErrorDetail> getDetails() {
        return details;
    }
}
