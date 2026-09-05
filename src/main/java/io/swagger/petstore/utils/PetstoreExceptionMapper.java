package io.swagger.petstore.utils;

import io.swagger.oas.inflector.models.ApiError;
import io.swagger.oas.inflector.utils.ApiException;
import io.swagger.petstore.model.ErrorResponse;

import javax.ws.rs.WebApplicationException;
import javax.ws.rs.core.Context;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.Response;
import javax.ws.rs.core.UriInfo;
import javax.ws.rs.ext.ExceptionMapper;
import javax.ws.rs.ext.Provider;
import java.util.Collections;

/** Converts both Inflector input errors and application failures to the public error contract. */
@Provider
public class PetstoreExceptionMapper implements ExceptionMapper<Exception> {
    @Context
    private UriInfo uriInfo;

    @Override
    public Response toResponse(Exception exception) {
        final int status = status(exception);
        final ErrorIdentity identity = identity(status, sourceMessage(exception), path());
        return Response.status(status)
                .type(MediaType.APPLICATION_JSON_TYPE)
                .entity(new ErrorResponse(status, identity.error, identity.message,
                        Collections.emptyList()))
                .build();
    }

    private int status(Exception exception) {
        if (exception instanceof ApiException) {
            final ApiError error = ((ApiException) exception).getError();
            return error == null ? 500 : error.getCode();
        }
        if (exception instanceof WebApplicationException) {
            return ((WebApplicationException) exception).getResponse().getStatus();
        }
        return 500;
    }

    private String sourceMessage(Exception exception) {
        if (exception instanceof ApiException) {
            final ApiError error = ((ApiException) exception).getError();
            return error == null ? null : error.getMessage();
        }
        return exception.getMessage();
    }

    private String path() {
        return uriInfo == null ? "" : "/" + uriInfo.getPath();
    }

    static ErrorIdentity identity(int status, String source, String path) {
        final String message = source == null ? "" : source;
        final String requestPath = path == null ? "" : path;
        if (status == 400) {
            if (message.contains("missing required query parameter `status`")) {
                return new ErrorIdentity("BAD_REQUEST", "Status is required");
            }
            if (message.contains("missing required query parameter `tags`")) {
                return new ErrorIdentity("BAD_REQUEST", "At least one tag is required");
            }
            if (message.contains("missing required query parameter `code`")) {
                if (requestPath.contains("/auth/confirm/")) {
                    return new ErrorIdentity("INVALID_CONFIRMATION_LINK", "The one-time link is invalid");
                }
                if (requestPath.contains("/auth/password/reset/")) {
                    return new ErrorIdentity("INVALID_RESET_LINK", "The one-time link is invalid");
                }
            }
            if (message.contains("couldn't convert") || message.contains("cannot convert")) {
                if (requestPath.contains("/store/order/")) {
                    return new ErrorIdentity("BAD_REQUEST", "Order id must be a valid UUID");
                }
                if (requestPath.contains("/admin/users/")
                        || requestPath.contains("/auth/confirm/")
                        || requestPath.contains("/auth/password/reset/")) {
                    return new ErrorIdentity("BAD_REQUEST", "User id must be a valid UUID");
                }
                if (requestPath.contains("/pet/")) {
                    return new ErrorIdentity("BAD_REQUEST", "Pet id must be a valid UUID");
                }
            }
            if (message.contains("input body") && message.contains("required")) {
                return new ErrorIdentity("BAD_REQUEST", "Request body is required");
            }
            if (message.contains("unable to convert input")) {
                return new ErrorIdentity("BAD_REQUEST", "Request body contains malformed or incompatible JSON");
            }
            return new ErrorIdentity("BAD_REQUEST", "Request parameters are invalid");
        }
        if (status == 404) {
            return new ErrorIdentity("NOT_FOUND", "The requested endpoint was not found");
        }
        if (status == 405) {
            return new ErrorIdentity("METHOD_NOT_ALLOWED", "The HTTP method is not allowed for this endpoint");
        }
        if (status == 415) {
            return new ErrorIdentity("UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json");
        }
        return new ErrorIdentity("INTERNAL_SERVER_ERROR", "An unexpected error occurred");
    }

    static final class ErrorIdentity {
        private final String error;
        private final String message;

        private ErrorIdentity(String error, String message) {
            this.error = error;
            this.message = message;
        }

        String getError() {
            return error;
        }

        String getMessage() {
            return message;
        }
    }
}
