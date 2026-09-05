package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.LoginRequest;
import io.swagger.petstore.model.LoginResponse;
import io.swagger.petstore.model.PasswordForgotRequest;
import io.swagger.petstore.model.PasswordResetLinkResponse;
import io.swagger.petstore.model.PasswordResetRequest;
import io.swagger.petstore.service.AccountException;
import io.swagger.petstore.service.AuthService;
import io.swagger.petstore.service.ValidationService;
import io.swagger.petstore.utils.Responses;
import io.swagger.petstore.utils.Util;

import javax.ws.rs.core.Response;
import java.util.List;
import java.util.UUID;

public class AuthenticationController {
    private final AuthService authService = AuthService.getInstance();

    public ResponseContext login(final RequestContext request, final LoginRequest body) {
        final String username = body == null ? null : body.getUsername();
        final String password = body == null ? null : body.getPassword();
        final List<ErrorDetail> errors = ValidationService.validateLogin(username, password);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        try {
            final LoginResponse response = authService.login(username, password);
            if (response == null) {
                return Responses.error(Response.Status.UNAUTHORIZED, "INVALID_CREDENTIALS",
                        "Username or password is incorrect");
            }
            return new ResponseContext().contentType(Util.getMediaType(request)).entity(response);
        } catch (AccountException exception) {
            return accountError(exception);
        }
    }

    public ResponseContext forgotPassword(final RequestContext request, final PasswordForgotRequest body) {
        final List<ErrorDetail> errors = ValidationService.validatePasswordForgot(body);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        try {
            final PasswordResetLinkResponse response = authService.forgotPassword(body.getEmail());
            return new ResponseContext().contentType(Util.getMediaType(request)).entity(response);
        } catch (AccountException exception) {
            return accountError(exception);
        }
    }

    public ResponseContext resetPassword(final RequestContext request, final UUID userId,
                                         final String code, final PasswordResetRequest body) {
        final List<ErrorDetail> errors = ValidationService.validatePasswordReset(body);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        if (userId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "User id must be a valid UUID");
        }
        try {
            authService.resetPassword(userId, code, body.getNewPassword());
            return new ResponseContext().status(Response.Status.NO_CONTENT);
        } catch (AccountException exception) {
            return accountError(exception);
        }
    }

    private ResponseContext accountError(AccountException exception) {
        return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
    }
}
