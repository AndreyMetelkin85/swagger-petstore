package io.swagger.petstore.service;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.petstore.data.UserData;
import io.swagger.petstore.model.AccountStatus;
import io.swagger.petstore.model.ConfirmationLinkResponse;
import io.swagger.petstore.model.LoginResponse;
import io.swagger.petstore.model.PasswordResetLinkResponse;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.RegistrationResponse;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;
import io.swagger.petstore.model.UserUpdateRequest;

import javax.ws.rs.core.HttpHeaders;
import javax.ws.rs.core.Response;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.Date;
import java.util.UUID;

public class AuthService {
    public static final long CONFIRMATION_TTL_HOURS = 24L;
    public static final long PASSWORD_RESET_TTL_MINUTES = 30L;
    private static final String DEFAULT_PUBLIC_BASE_URL = "http://localhost:8080/api/v3";
    private static final AuthService INSTANCE = new AuthService();

    private final UserData userData;
    private final TokenService tokenService;
    private final CredentialService credentialService;
    private final Clock clock;
    private final String publicBaseUrl;

    public AuthService() {
        this(new UserData(), new TokenService(), new CredentialService(), Clock.systemUTC(), configuredBaseUrl());
    }

    AuthService(UserData userData, TokenService tokenService, CredentialService credentialService,
                Clock clock, String publicBaseUrl) {
        this.userData = userData;
        this.tokenService = tokenService;
        this.credentialService = credentialService;
        this.clock = clock;
        this.publicBaseUrl = trimTrailingSlash(publicBaseUrl);
    }

    public static AuthService getInstance() {
        return INSTANCE;
    }

    public RegistrationResponse register(final RegisterRequest request) {
        final String code = credentialService.newOneTimeCode();
        final Instant expiresAt = clock.instant().plus(CONFIRMATION_TTL_HOURS, ChronoUnit.HOURS);
        final User user = UserData.createUser(null, request.getUsername(), request.getFirstName(),
                request.getLastName(), request.getEmail(),
                credentialService.hashPassword(request.getPassword()), request.getPhone(),
                AccountStatus.PENDING, Role.USER);
        if (!userData.addPendingUserIfAbsent(user, credentialService.hashOneTimeCode(code),
                Date.from(expiresAt))) {
            throw new AccountException(Response.Status.CONFLICT, "USER_ALREADY_EXISTS",
                    "A user with this username or email already exists");
        }
        return new RegistrationResponse(user, confirmationUrl(user.getId(), code), expiresAt.toString());
    }

    public ConfirmationLinkResponse resendConfirmation(final String username, final String password) {
        final User user = authenticatedUser(username, password);
        if (user == null) {
            throw new AccountException(Response.Status.UNAUTHORIZED, "INVALID_CREDENTIALS",
                    "Username or password is incorrect");
        }
        if (user.getConfirmedAt() != null) {
            throw new AccountException(Response.Status.CONFLICT, "ACCOUNT_ALREADY_CONFIRMED",
                    "The account has already been confirmed");
        }
        final String code = credentialService.newOneTimeCode();
        final Instant expiresAt = clock.instant().plus(CONFIRMATION_TTL_HOURS, ChronoUnit.HOURS);
        userData.setConfirmationLink(user.getId(), credentialService.hashOneTimeCode(code),
                Date.from(expiresAt));
        return new ConfirmationLinkResponse(confirmationUrl(user.getId(), code), expiresAt.toString());
    }

    public User confirm(final UUID userId, final String code) {
        final User user = requiredUser(userId);
        if (user.getConfirmedAt() != null) {
            throw new AccountException(Response.Status.CONFLICT, "ACCOUNT_ALREADY_CONFIRMED",
                    "The account has already been confirmed");
        }
        validateCode(code, user.getConfirmationCodeHash(), user.getConfirmationExpiresAt(),
                "INVALID_CONFIRMATION_LINK", "CONFIRMATION_LINK_EXPIRED");
        final User confirmed = userData.confirmUser(userId, user.getConfirmationCodeHash());
        if (confirmed == null) {
            final User current = requiredUser(userId);
            if (current.getConfirmedAt() != null) {
                throw new AccountException(Response.Status.CONFLICT, "ACCOUNT_ALREADY_CONFIRMED",
                        "The account has already been confirmed");
            }
            validateCode(code, current.getConfirmationCodeHash(), current.getConfirmationExpiresAt(),
                    "INVALID_CONFIRMATION_LINK", "CONFIRMATION_LINK_EXPIRED");
            throw new AccountException(Response.Status.CONFLICT, "CONFIRMATION_STATE_CHANGED",
                    "The confirmation state changed; request a new link");
        }
        return confirmed;
    }

    public PasswordResetLinkResponse forgotPassword(final String email) {
        final User user = userData.findUserByEmail(email);
        if (user == null) {
            throw new AccountException(Response.Status.NOT_FOUND, "USER_NOT_FOUND",
                    "A user with this email was not found");
        }
        final String code = credentialService.newOneTimeCode();
        final Instant expiresAt = clock.instant().plus(PASSWORD_RESET_TTL_MINUTES, ChronoUnit.MINUTES);
        userData.setResetLink(user.getId(), credentialService.hashOneTimeCode(code), Date.from(expiresAt));
        return new PasswordResetLinkResponse(resetUrl(user.getId(), code), expiresAt.toString());
    }

    public void resetPassword(final UUID userId, final String code, final String newPassword) {
        final User user = requiredUser(userId);
        if (user.getResetUsedAt() != null
                && credentialService.codeMatches(code, user.getResetCodeHash())) {
            throw new AccountException(Response.Status.CONFLICT, "RESET_LINK_ALREADY_USED",
                    "The password reset link has already been used");
        }
        validateCode(code, user.getResetCodeHash(), user.getResetExpiresAt(),
                "INVALID_RESET_LINK", "RESET_LINK_EXPIRED");
        final User reset = userData.resetPassword(userId, user.getResetCodeHash(),
                credentialService.hashPassword(newPassword));
        if (reset == null) {
            final User current = requiredUser(userId);
            if (current.getResetUsedAt() != null
                    && credentialService.codeMatches(code, current.getResetCodeHash())) {
                throw new AccountException(Response.Status.CONFLICT, "RESET_LINK_ALREADY_USED",
                        "The password reset link has already been used");
            }
            validateCode(code, current.getResetCodeHash(), current.getResetExpiresAt(),
                    "INVALID_RESET_LINK", "RESET_LINK_EXPIRED");
            throw new AccountException(Response.Status.CONFLICT, "RESET_STATE_CHANGED",
                    "The password reset state changed; request a new link");
        }
    }

    public LoginResponse login(final String username, final String password) {
        final User user = authenticatedUser(username, password);
        if (user == null) {
            return null;
        }
        ensureAccountCanAuthenticate(user);
        return new LoginResponse(tokenService.issueToken(user), TokenService.DEFAULT_TTL_SECONDS, user);
    }

    public User updateCurrentUser(final User currentUser, final UserUpdateRequest update) {
        if (update.getEmail() != null) {
            final User owner = userData.findUserByEmail(update.getEmail());
            if (owner != null && !owner.getId().equals(currentUser.getId())) {
                throw new AccountException(Response.Status.CONFLICT, "EMAIL_ALREADY_EXISTS",
                        "A user with this email already exists");
            }
        }
        if (update.getPassword() != null) {
            update.setPassword(credentialService.hashPassword(update.getPassword()));
        }
        return userData.updateUser(currentUser.getUsername(), update);
    }

    public User blockUser(final User actor, final UUID userId) {
        final User target = manageableUser(actor, userId);
        if (target.getUserStatus() == AccountStatus.BLOCKED) {
            throw invalidTransition("The account is already blocked");
        }
        final User updated = userData.setStatus(userId, target.getUserStatus(), AccountStatus.BLOCKED, true);
        if (updated == null) {
            throw invalidTransition("The account status changed before it could be blocked");
        }
        return updated;
    }

    public User unblockUser(final User actor, final UUID userId) {
        final User target = manageableUser(actor, userId);
        if (target.getUserStatus() != AccountStatus.BLOCKED) {
            throw invalidTransition("The account is not blocked");
        }
        final AccountStatus restored = target.getConfirmedAt() == null
                ? AccountStatus.PENDING : AccountStatus.ACTIVE;
        final User updated = userData.setStatus(userId, AccountStatus.BLOCKED, restored, false);
        if (updated == null) {
            throw invalidTransition("The account status changed before it could be unblocked");
        }
        return updated;
    }

    public AuthResult authorize(final RequestContext request, final Role... allowedRoles) {
        final String authorization = request == null || request.getHeaders() == null
                ? null : request.getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        if (authorization == null || authorization.trim().isEmpty()) {
            return AuthResult.failure(Response.Status.UNAUTHORIZED, "UNAUTHORIZED",
                    "Bearer token is required");
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
            if (user.getUserStatus() == AccountStatus.BLOCKED) {
                return AuthResult.failure(Response.Status.FORBIDDEN, "ACCOUNT_BLOCKED",
                        "The account is blocked");
            }
            if (user.getUserStatus() == AccountStatus.PENDING) {
                return AuthResult.failure(Response.Status.FORBIDDEN, "ACCOUNT_NOT_VERIFIED",
                        "The account has not been confirmed");
            }
            if (user.getTokenVersion() != claims.getTokenVersion()) {
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

    private User authenticatedUser(String username, String password) {
        final User user = userData.findUserByName(username);
        if (user == null || !credentialService.passwordMatches(password, user.getPassword())) {
            return null;
        }
        if (!credentialService.isBcrypt(user.getPassword())) {
            final String upgraded = credentialService.hashPassword(password);
            userData.replacePasswordIfCurrent(user.getUsername(), user.getPassword(), upgraded);
            user.setPassword(upgraded);
        }
        return user;
    }

    private void ensureAccountCanAuthenticate(User user) {
        if (user.getUserStatus() == AccountStatus.PENDING) {
            throw new AccountException(Response.Status.FORBIDDEN, "ACCOUNT_NOT_VERIFIED",
                    "The account has not been confirmed");
        }
        if (user.getUserStatus() == AccountStatus.BLOCKED) {
            throw new AccountException(Response.Status.FORBIDDEN, "ACCOUNT_BLOCKED",
                    "The account is blocked");
        }
    }

    private User manageableUser(User actor, UUID userId) {
        final User target = requiredUser(userId);
        if (actor.getId().equals(target.getId()) || target.getRole() == Role.ADMIN) {
            throw new AccountException(Response.Status.FORBIDDEN, "ADMIN_ACCOUNT_PROTECTED",
                    "Administrator accounts cannot be managed by this operation");
        }
        return target;
    }

    private User requiredUser(UUID userId) {
        final User user = userData.findUserById(userId);
        if (user == null) {
            throw new AccountException(Response.Status.NOT_FOUND, "USER_NOT_FOUND", "User was not found");
        }
        return user;
    }

    private void validateCode(String code, String storedHash, Date expiresAt,
                              String invalidCode, String expiredCode) {
        if (!credentialService.codeMatches(code, storedHash)) {
            throw new AccountException(Response.Status.BAD_REQUEST, invalidCode,
                    "The one-time link is invalid");
        }
        if (expiresAt == null || !expiresAt.toInstant().isAfter(clock.instant())) {
            throw new AccountException(Response.Status.GONE, expiredCode,
                    "The one-time link has expired");
        }
    }

    private AccountException invalidTransition(String message) {
        return new AccountException(Response.Status.CONFLICT, "INVALID_STATUS_TRANSITION", message);
    }

    private String confirmationUrl(UUID userId, String code) {
        return publicBaseUrl + "/auth/confirm/" + userId + "?code=" + code;
    }

    private String resetUrl(UUID userId, String code) {
        return publicBaseUrl + "/auth/password/reset/" + userId + "?code=" + code;
    }

    private static String configuredBaseUrl() {
        final String configured = System.getenv("PETSTORE_PUBLIC_BASE_URL");
        return configured == null || configured.trim().isEmpty() ? DEFAULT_PUBLIC_BASE_URL : configured.trim();
    }

    private static String trimTrailingSlash(String value) {
        String result = value == null ? DEFAULT_PUBLIC_BASE_URL : value.trim();
        while (result.endsWith("/")) {
            result = result.substring(0, result.length() - 1);
        }
        return result;
    }
}
