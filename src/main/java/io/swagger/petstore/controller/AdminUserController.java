package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;
import io.swagger.petstore.service.AccountException;
import io.swagger.petstore.service.AuthResult;
import io.swagger.petstore.service.AuthService;
import io.swagger.petstore.utils.Responses;
import io.swagger.petstore.utils.Util;

import javax.ws.rs.core.Response;
import java.util.UUID;

public class AdminUserController {
    private final AuthService authService = AuthService.getInstance();

    public ResponseContext blockUser(final RequestContext request, final UUID userId) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (userId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "User id must be a valid UUID");
        }
        try {
            final User user = authService.blockUser(auth.getUser(), userId);
            return new ResponseContext().contentType(Util.getMediaType(request)).entity(user);
        } catch (AccountException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

    public ResponseContext unblockUser(final RequestContext request, final UUID userId) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (userId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "User id must be a valid UUID");
        }
        try {
            final User user = authService.unblockUser(auth.getUser(), userId);
            return new ResponseContext().contentType(Util.getMediaType(request)).entity(user);
        } catch (AccountException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }
}
