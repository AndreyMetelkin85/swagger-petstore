package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.data.UserData;
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

public class UserController {
    private final AuthService authService = AuthService.getInstance();
    private final UserData userData = authService.getUserData();

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

    public ResponseContext getUserByName(final RequestContext request, final String username) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final User user = userData.findUserByName(username);
        if (user == null) {
            return Responses.error(Response.Status.NOT_FOUND, "USER_NOT_FOUND", "User was not found");
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(user);
    }

}
