package io.swagger.petstore.service;

import io.swagger.petstore.model.ErrorDetail;

import javax.ws.rs.core.Response;
import java.util.Collections;
import java.util.List;

/** Expected order-domain failure mapped by the controller to the public error contract. */
public class OrderException extends RuntimeException {
    private final Response.Status status;
    private final String code;
    private final List<ErrorDetail> details;

    public OrderException(final Response.Status status, final String code, final String message) {
        this(status, code, message, Collections.<ErrorDetail>emptyList());
    }

    public OrderException(final Response.Status status, final String code, final String message,
                          final List<ErrorDetail> details) {
        super(message);
        this.status = status;
        this.code = code;
        this.details = details == null ? Collections.<ErrorDetail>emptyList() : details;
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
