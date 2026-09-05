package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.model.ConfirmationLinkResponse;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.LoginRequest;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.RegistrationResponse;
import io.swagger.petstore.model.User;
import io.swagger.petstore.service.AccountException;
import io.swagger.petstore.service.AuthService;
import io.swagger.petstore.service.ValidationService;
import io.swagger.petstore.utils.Responses;
import io.swagger.petstore.utils.Util;

import javax.ws.rs.core.Response;
import java.util.List;
import java.util.UUID;

public class RegistrationController {
    private final AuthService authService = AuthService.getInstance();

    public ResponseContext register(final RequestContext request, final RegisterRequest body) {
        final List<ErrorDetail> errors = ValidationService.validateRegistration(body);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        try {
            final RegistrationResponse created = authService.register(body);
            return new ResponseContext()
                    .status(Response.Status.CREATED)
                    .contentType(Util.getMediaType(request))
                    .entity(created);
        } catch (AccountException exception) {
            return accountError(exception);
        }
    }

    public ResponseContext confirm(final RequestContext request, final UUID userId, final String code) {
        if (userId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "User id must be a valid UUID");
        }
        try {
            final User confirmed = authService.confirm(userId, code);
            return new ResponseContext().contentType(Util.getMediaType(request)).entity(confirmed);
        } catch (AccountException exception) {
            return accountError(exception);
        }
    }

    public ResponseContext resendConfirmation(final RequestContext request, final LoginRequest body) {
        final String username = body == null ? null : body.getUsername();
        final String password = body == null ? null : body.getPassword();
        final List<ErrorDetail> errors = ValidationService.validateLogin(username, password);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        try {
            final ConfirmationLinkResponse response = authService.resendConfirmation(username, password);
            return new ResponseContext().contentType(Util.getMediaType(request)).entity(response);
        } catch (AccountException exception) {
            return accountError(exception);
        }
    }

    private ResponseContext accountError(AccountException exception) {
        return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
    }
}
