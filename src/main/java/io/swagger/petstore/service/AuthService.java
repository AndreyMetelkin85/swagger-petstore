package io.swagger.petstore.service;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.petstore.data.UserData;
import io.swagger.petstore.model.LoginResponse;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;

import javax.ws.rs.core.HttpHeaders;
import javax.ws.rs.core.Response;
import java.util.Arrays;

public class AuthService {
    private static final AuthService INSTANCE = new AuthService();

    private final UserData userData = new UserData();
    private final TokenService tokenService = new TokenService();

    public static AuthService getInstance() {
        return INSTANCE;
    }

    public User register(final RegisterRequest request) {
        final User user = UserData.createUser(null, request.getUsername(), request.getFirstName(),
                request.getLastName(), request.getEmail(), request.getPassword(), request.getPhone(),
                1, Role.USER);
        return userData.addUserIfAbsent(user) ? user : null;
    }

    public LoginResponse login(final String username, final String password) {
        final User user = userData.authenticate(username, password);
        if (user == null) {
            return null;
        }
        return new LoginResponse(tokenService.issueToken(user), TokenService.DEFAULT_TTL_SECONDS, user);
    }

    public AuthResult authorize(final RequestContext request, final Role... allowedRoles) {
        final String authorization = request == null || request.getHeaders() == null
                ? null : request.getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        if (authorization == null || authorization.trim().isEmpty()) {
            return AuthResult.failure(Response.Status.UNAUTHORIZED, "UNAUTHORIZED",
                    "Bearer access token is required");
        }
        if (!authorization.regionMatches(true, 0, "Bearer ", 0, 7)
                || authorization.substring(7).trim().isEmpty()) {
            return AuthResult.failure(Response.Status.UNAUTHORIZED, "INVALID_TOKEN",
                    "Authorization header must use the Bearer scheme");
        }

        try {
            final TokenService.TokenClaims claims = tokenService.validate(authorization.substring(7).trim());
            final User user = userData.findUserByName(claims.getUsername());
            if (user == null || user.getRole() != claims.getRole()) {
                return AuthResult.failure(Response.Status.UNAUTHORIZED, "INVALID_TOKEN",
                        "Access token is invalid");
            }
            if (allowedRoles != null && allowedRoles.length > 0
                    && !Arrays.asList(allowedRoles).contains(user.getRole())) {
                return AuthResult.failure(Response.Status.FORBIDDEN, "FORBIDDEN",
                        "The current role is not allowed to perform this operation");
            }
            return AuthResult.success(user);
        } catch (TokenException exception) {
            return AuthResult.failure(Response.Status.UNAUTHORIZED, exception.getCode(),
                    exception.getMessage());
        }
    }

    public UserData getUserData() {
        return userData;
    }
}
