package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.LoginRequest;
import io.swagger.petstore.model.LoginResponse;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.User;
import io.swagger.petstore.service.AuthService;
import io.swagger.petstore.service.ValidationService;
import io.swagger.petstore.utils.Responses;
import io.swagger.petstore.utils.Util;

import javax.ws.rs.core.Response;
import java.util.List;

public class AuthController {
    private final AuthService authService = AuthService.getInstance();

    public ResponseContext register(final RequestContext request, final RegisterRequest body) {
        final List<ErrorDetail> errors = ValidationService.validateRegistration(body);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        final User created = authService.register(body);
        if (created == null) {
            return Responses.error(Response.Status.CONFLICT, "USER_ALREADY_EXISTS",
                    "A user with this username already exists");
        }
        return new ResponseContext()
                .status(Response.Status.CREATED)
                .contentType(Util.getMediaType(request))
                .entity(created);
    }

    public ResponseContext login(final RequestContext request, final LoginRequest body) {
        final String username = body == null ? null : body.getUsername();
        final String password = body == null ? null : body.getPassword();
        final List<ErrorDetail> errors = ValidationService.validateLogin(username, password);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        final LoginResponse response = authService.login(username, password);
        if (response == null) {
            return Responses.error(Response.Status.UNAUTHORIZED, "INVALID_CREDENTIALS",
                    "Username or password is incorrect");
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(response);
    }
}
