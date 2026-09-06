package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.model.AdminUserUpdateRequest;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;
import io.swagger.petstore.model.UserUpdateRequest;
import io.swagger.petstore.service.AuthResult;
import io.swagger.petstore.service.AuthService;
import io.swagger.petstore.service.AccountException;
import io.swagger.petstore.service.ValidationService;
import io.swagger.petstore.utils.Responses;
import io.swagger.petstore.utils.Util;

import javax.ws.rs.core.Response;
import java.util.List;
import java.util.UUID;

public class UserController {
    private final AuthService authService = AuthService.getInstance();

    public ResponseContext getCurrentUser(final RequestContext request) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(auth.getUser());
    }

    public ResponseContext updateCurrentUser(final RequestContext request, final UserUpdateRequest body) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final List<ErrorDetail> errors = ValidationService.validateUserUpdate(body);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        try {
            final User updated = authService.updateCurrentUser(auth.getUser(), body);
            return new ResponseContext()
                    .contentType(Util.getMediaType(request))
                    .entity(updated);
        } catch (AccountException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

    public ResponseContext listUsers(final RequestContext request) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(authService.listUsers());
    }

    public ResponseContext getUserById(final RequestContext request, final UUID userId) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (userId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "User id must be a valid UUID");
        }
        try {
            return new ResponseContext()
                    .contentType(Util.getMediaType(request))
                    .entity(authService.getUser(userId));
        } catch (AccountException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

    public ResponseContext updateUserById(final RequestContext request, final UUID userId,
                                          final AdminUserUpdateRequest body) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (userId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "User id must be a valid UUID");
        }
        final List<ErrorDetail> errors = ValidationService.validateAdminUserUpdate(body);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        try {
            final User updated = authService.updateUserAsAdmin(userId, body);
            return new ResponseContext()
                    .contentType(Util.getMediaType(request))
                    .entity(updated);
        } catch (AccountException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

}
