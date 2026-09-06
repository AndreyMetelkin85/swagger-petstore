package io.swagger.petstore.service;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.petstore.data.UserData;
import io.swagger.petstore.model.AdminUserUpdateRequest;
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
import java.time.Duration;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.UUID;

public class AuthService {
    public static final long CONFIRMATION_TTL_HOURS = 24L;
    public static final long PASSWORD_RESET_TTL_MINUTES = 30L;
    private static final int MAX_LOGIN_ATTEMPTS = 5;
    private static final long LOGIN_FAILURE_WINDOW_MINUTES = 5L;
    private static final long LOGIN_LOCKOUT_MINUTES = 5L;
    private static final String DEFAULT_PUBLIC_BASE_URL = "http://localhost:8080/api/v3";
    private static final AuthService INSTANCE = new AuthService();

    private final UserData userData;
    private final TokenService tokenService;
    private final CredentialService credentialService;
    private final Clock clock;
    private final String publicBaseUrl;
    private final boolean exposeTestLinks;
    private final Map<String, LoginAttempts> loginAttemptsByIdentifier;

    public AuthService() {
        this(new UserData(), new TokenService(), new CredentialService(), Clock.systemUTC(), configuredBaseUrl(),
                configuredTestLinkExposure());
    }

    AuthService(UserData userData, TokenService tokenService, CredentialService credentialService,
                Clock clock, String publicBaseUrl) {
        this(userData, tokenService, credentialService, clock, publicBaseUrl, true);
    }

    AuthService(UserData userData, TokenService tokenService, CredentialService credentialService,
                Clock clock, String publicBaseUrl, boolean exposeTestLinks) {
        this.userData = userData;
        this.tokenService = tokenService;
        this.credentialService = credentialService;
        this.clock = clock;
        this.publicBaseUrl = trimTrailingSlash(publicBaseUrl);
        this.exposeTestLinks = exposeTestLinks;
        this.loginAttemptsByIdentifier = new ConcurrentHashMap<>();
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
        user.setAddress(request.getAddress());
        if (!userData.addPendingUserIfAbsent(user, credentialService.hashOneTimeCode(code),
                Date.from(expiresAt))) {
            throw new AccountException(Response.Status.CONFLICT, "USER_ALREADY_EXISTS",
                    "A user with this username or email already exists");
        }
        return new RegistrationResponse(user, confirmationUrl(user.getId(), code), expiresAt.toString());
    }

    public ConfirmationLinkResponse resendConfirmation(final String email, final String password) {
        final User user = rateLimitedAuthenticatedUser(email, password);
        if (user == null) {
            throw new AccountException(Response.Status.UNAUTHORIZED, "INVALID_CREDENTIALS",
                    "Email or password is incorrect");
        }
        if (user.getConfirmedAt() != null) {
            throw new AccountException(Response.Status.CONFLICT, "ACCOUNT_ALREADY_CONFIRMED",
                    "The account has already been confirmed");
        }
        final String code = credentialService.newOneTimeCode();
        final Instant expiresAt = clock.instant().plus(CONFIRMATION_TTL_HOURS, ChronoUnit.HOURS);
        final User updated = userData.setConfirmationLink(user.getId(),
                credentialService.hashOneTimeCode(code), Date.from(expiresAt));
        if (updated == null) {
            final User current = requiredUser(user.getId());
            if (current.getConfirmedAt() != null) {
                throw new AccountException(Response.Status.CONFLICT, "ACCOUNT_ALREADY_CONFIRMED",
                        "The account has already been confirmed");
            }
            throw new AccountException(Response.Status.CONFLICT, "CONFIRMATION_STATE_CHANGED",
                    "The confirmation state changed; retry the request");
        }
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
        final String resetUrl = exposeTestLinks ? resetUrl(user.getId(), code) : null;
        return new PasswordResetLinkResponse(resetUrl, expiresAt.toString());
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
        clearFailedLoginAttempt(normalizeIdentifier(reset.getEmail()));
    }

    public LoginResponse login(final String email, final String password) {
        final User user = rateLimitedAuthenticatedUser(email, password);
        if (user == null) {
            return null;
        }
        ensureAccountCanAuthenticate(user);
        return new LoginResponse(tokenService.issueToken(user), TokenService.DEFAULT_TTL_SECONDS, user);
    }

    public User updateCurrentUser(final User currentUser, final UserUpdateRequest update) {
        final User updated = userData.updateUser(currentUser.getUsername(), update);
        if (updated == null) {
            throw new AccountException(Response.Status.NOT_FOUND, "USER_NOT_FOUND", "User was not found");
        }
        return updated;
    }

    public List<User> listUsers() {
        return userData.findAll();
    }

    public User getUser(final UUID userId) {
        return requiredUser(userId);
    }

    public User updateUserAsAdmin(final UUID userId, final AdminUserUpdateRequest update) {
        final User target = requiredUser(userId);
        final String normalizedEmail = update.getEmail().trim().toLowerCase(Locale.ROOT);
        final User usernameOwner = userData.findUserByName(update.getUsername());
        if (usernameOwner != null && !usernameOwner.getId().equals(target.getId())) {
            throw new AccountException(Response.Status.CONFLICT, "USERNAME_ALREADY_EXISTS",
                    "A user with this username already exists");
        }
        final User emailOwner = userData.findUserByEmail(normalizedEmail);
        if (emailOwner != null && !emailOwner.getId().equals(target.getId())) {
            throw new AccountException(Response.Status.CONFLICT, "EMAIL_ALREADY_EXISTS",
                    "A user with this email already exists");
        }
        if (update.getRole() == Role.ADMIN && target.getRole() != Role.ADMIN
                && target.getUserStatus() != AccountStatus.ACTIVE) {
            throw new AccountException(Response.Status.CONFLICT, "INVALID_ROLE_TRANSITION",
                    "Only an active user can be promoted to administrator");
        }
        try {
            final User updated = userData.updateUserAsAdmin(userId, update, normalizedEmail);
            if (updated == null) {
                throw new AccountException(Response.Status.NOT_FOUND, "USER_NOT_FOUND", "User was not found");
            }
            return updated;
        } catch (UserData.EmailAlreadyExistsException exception) {
            throw new AccountException(Response.Status.CONFLICT, "EMAIL_ALREADY_EXISTS",
                    "A user with this email already exists");
        } catch (UserData.UsernameAlreadyExistsException exception) {
            throw new AccountException(Response.Status.CONFLICT, "USERNAME_ALREADY_EXISTS",
                    "A user with this username already exists");
        } catch (UserData.LastAdministratorException exception) {
            throw new AccountException(Response.Status.CONFLICT, "LAST_ADMIN_PROTECTED",
                    "The last administrator cannot be demoted");
        } catch (UserData.InvalidRoleTransitionException exception) {
            throw new AccountException(Response.Status.CONFLICT, "INVALID_ROLE_TRANSITION",
                    "Only an active user can be promoted to administrator");
        }
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

    private String normalizeIdentifier(final String identifier) {
        return identifier == null ? null : identifier.trim().toLowerCase(Locale.ROOT);
    }

    private void enforceLoginRateLimit(final String normalizedIdentifier) {
        if (normalizedIdentifier == null || normalizedIdentifier.isEmpty()) {
            return;
        }
        final Instant now = clock.instant();
        final LoginAttempts attempts = loginAttemptsByIdentifier.get(normalizedIdentifier);
        if (attempts == null) {
            return;
        }
        if (attempts.isExpired(now)) {
            loginAttemptsByIdentifier.remove(normalizedIdentifier);
            return;
        }
        if (attempts.isLocked(now)) {
            final long remainingSeconds = Math.max(0L, Duration.between(now,
                    attempts.getBlockedUntil()).getSeconds());
            final long remainingMinutes = Math.max(1L, (remainingSeconds + 59) / 60);
            throw new AccountException(Response.Status.TOO_MANY_REQUESTS, "LOGIN_RATE_LIMITED",
                    "Too many failed login attempts. Try again in " + remainingMinutes + " minute(s)");
        }
    }

    private void incrementFailedLoginAttempt(final String normalizedIdentifier) {
        if (normalizedIdentifier == null || normalizedIdentifier.isEmpty()) {
            return;
        }
        final Instant now = clock.instant();
        loginAttemptsByIdentifier.compute(normalizedIdentifier, (identifier, current) -> {
            if (current == null || current.isExpired(now)) {
                return new LoginAttempts(now, 1, null);
            }
            if (current.isLocked(now)) {
                return current;
            }
            final int attempts = current.getAttempts() + 1;
            final Instant blockedUntil = attempts >= MAX_LOGIN_ATTEMPTS
                    ? now.plus(Duration.ofMinutes(LOGIN_LOCKOUT_MINUTES))
                    : null;
            return new LoginAttempts(current.getWindowStart(), attempts, blockedUntil);
        });
        final LoginAttempts state = loginAttemptsByIdentifier.get(normalizedIdentifier);
        if (state != null && state.isLocked(now)) {
            final long remainingSeconds = Math.max(0L, Duration.between(now,
                    state.getBlockedUntil()).getSeconds());
            final long remainingMinutes = Math.max(1L, (remainingSeconds + 59) / 60);
            throw new AccountException(Response.Status.TOO_MANY_REQUESTS, "LOGIN_RATE_LIMITED",
                    "Too many failed login attempts. Try again in " + remainingMinutes + " minute(s)");
        }
    }

    private void clearFailedLoginAttempt(final String normalizedIdentifier) {
        if (normalizedIdentifier == null || normalizedIdentifier.isEmpty()) {
            return;
        }
        loginAttemptsByIdentifier.remove(normalizedIdentifier);
    }

    private User rateLimitedAuthenticatedUser(final String email, final String password) {
        final String normalizedEmail = normalizeIdentifier(email);
        enforceLoginRateLimit(normalizedEmail);
        final User user = authenticatedUser(email, password);
        if (user == null) {
            incrementFailedLoginAttempt(normalizedEmail);
            return null;
        }
        clearFailedLoginAttempt(normalizedEmail);
        return user;
    }

    private User authenticatedUser(String email, String password) {
        final User user = userData.findUserByEmail(email);
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

    private static boolean configuredTestLinkExposure() {
        return Boolean.parseBoolean(System.getenv("PETSTORE_EXPOSE_TEST_LINKS"));
    }

    private static String trimTrailingSlash(String value) {
        String result = value == null ? DEFAULT_PUBLIC_BASE_URL : value.trim();
        while (result.endsWith("/")) {
            result = result.substring(0, result.length() - 1);
        }
        return result;
    }

    private static final class LoginAttempts {
        private final Instant windowStart;
        private final int attempts;
        private final Instant blockedUntil;
        private static final long ATTEMPTS_WINDOW_MINUTES = LOGIN_FAILURE_WINDOW_MINUTES;

        private LoginAttempts(Instant windowStart, int attempts, Instant blockedUntil) {
            this.windowStart = windowStart;
            this.attempts = attempts;
            this.blockedUntil = blockedUntil;
        }

        private Instant getWindowStart() {
            return windowStart;
        }

        private int getAttempts() {
            return attempts;
        }

        private Instant getBlockedUntil() {
            return blockedUntil;
        }

        private boolean isExpired(final Instant now) {
            final Instant expiresAt = blockedUntil == null
                    ? windowStart.plus(Duration.ofMinutes(ATTEMPTS_WINDOW_MINUTES))
                    : blockedUntil;
            return !now.isBefore(expiresAt);
        }

        private boolean isLocked(final Instant now) {
            return blockedUntil != null && now.isBefore(blockedUntil);
        }
    }
}
