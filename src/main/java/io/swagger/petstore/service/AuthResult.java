package io.swagger.petstore.service;

import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.model.ErrorResponse;
import io.swagger.petstore.model.User;

import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.Response;

public class AuthResult {
    private final User user;
    private final Response.Status errorStatus;
    private final ErrorResponse error;

    private AuthResult(User user, Response.Status errorStatus, ErrorResponse error) {
        this.user = user;
        this.errorStatus = errorStatus;
        this.error = error;
    }

    public static AuthResult success(User user) {
        return new AuthResult(user, null, null);
    }

    public static AuthResult failure(Response.Status status, String error, String message) {
        return new AuthResult(null, status,
                new ErrorResponse(status.getStatusCode(), error, message));
    }

    public boolean isAuthorized() {
        return user != null;
    }

    public User getUser() {
        return user;
    }

    public ResponseContext toResponse() {
        return new ResponseContext()
                .status(errorStatus)
                .contentType(MediaType.APPLICATION_JSON_TYPE)
                .entity(error);
    }
}
