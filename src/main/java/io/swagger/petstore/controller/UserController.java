package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.data.UserData;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.LoginResponse;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.RegistrationResponse;
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

    /** Backward-compatible alias for POST /auth/register. */
    public ResponseContext createUser(final RequestContext request, final User user) {
        final RegisterRequest registration = toRegistration(user);
        final List<ErrorDetail> errors = ValidationService.validateRegistration(registration);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        try {
            final RegistrationResponse created = authService.register(registration);
            return new ResponseContext()
                    .status(Response.Status.CREATED)
                    .contentType(Util.getMediaType(request))
                    .entity(created);
        } catch (AccountException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

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

    public ResponseContext deleteCurrentUser(final RequestContext request) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        userData.deleteUser(auth.getUser().getUsername());
        return new ResponseContext().status(Response.Status.NO_CONTENT);
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

    public ResponseContext createUsersWithListInput(final RequestContext request, final User[] users) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (users == null || users.length == 0) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "At least one user is required");
        }
        for (User user : users) {
            if (user.getRole() == null) {
                user.setRole(Role.USER);
            }
            userData.addUser(user);
        }
        return new ResponseContext()
                .status(Response.Status.CREATED)
                .contentType(Util.getMediaType(request))
                .entity(users);
    }

    /** Backward-compatible query-parameter login. */
    public ResponseContext loginUser(final RequestContext request, final String username, final String password) {
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
            return new ResponseContext()
                    .contentType(Util.getMediaType(request))
                    .header("X-Expires-In", String.valueOf(response.getExpiresIn()))
                    .entity(response);
        } catch (AccountException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

    public ResponseContext logoutUser(final RequestContext request) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        return new ResponseContext().status(Response.Status.NO_CONTENT);
    }

    public ResponseContext deleteUser(final RequestContext request, final String username) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (userData.findUserByName(username) == null) {
            return Responses.error(Response.Status.NOT_FOUND, "USER_NOT_FOUND", "User was not found");
        }
        userData.deleteUser(username);
        return new ResponseContext().status(Response.Status.NO_CONTENT);
    }

    public ResponseContext updateUser(final RequestContext request, final String username, final User user) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (user == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST", "Request body is required");
        }
        if (userData.findUserByName(username) == null) {
            return Responses.error(Response.Status.NOT_FOUND, "USER_NOT_FOUND", "User was not found");
        }
        user.setUsername(username);
        if (user.getRole() == null) {
            user.setRole(Role.USER);
        }
        userData.addUser(user);
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(user);
    }

    private RegisterRequest toRegistration(User user) {
        if (user == null) {
            return null;
        }
        final RegisterRequest result = new RegisterRequest();
        result.setUsername(user.getUsername());
        result.setPassword(user.getPassword());
        result.setEmail(user.getEmail());
        result.setFirstName(user.getFirstName());
        result.setLastName(user.getLastName());
        result.setPhone(user.getPhone());
        return result;
    }
}
