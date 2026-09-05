package io.swagger.petstore.utils;

import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.ErrorResponse;

import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.Response;
import java.util.Collections;
import java.util.List;

public final class Responses {
    private Responses() {
    }

    public static ResponseContext error(Response.Status status, String error, String message) {
        return error(status, error, message, Collections.<ErrorDetail>emptyList());
    }

    public static ResponseContext error(Response.Status status, String error, String message,
                                        List<ErrorDetail> details) {
        return new ResponseContext()
                .status(status)
                .contentType(MediaType.APPLICATION_JSON_TYPE)
                .entity(new ErrorResponse(status.getStatusCode(), error, message, details));
    }

    public static ResponseContext validation(List<ErrorDetail> details) {
        return new ResponseContext()
                .status(422)
                .contentType(MediaType.APPLICATION_JSON_TYPE)
                .entity(new ErrorResponse(422, "VALIDATION_ERROR", "Request validation failed", details));
    }
}
