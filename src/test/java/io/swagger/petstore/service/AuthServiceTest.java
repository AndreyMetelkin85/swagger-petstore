package io.swagger.petstore.service;

import io.swagger.petstore.data.UserData;
import io.swagger.petstore.model.AccountStatus;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.PasswordResetLinkResponse;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;
import org.junit.Test;

import javax.ws.rs.core.Response;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Date;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class AuthServiceTest {
    private static final UUID USER_ID = UUID.fromString("b9ec3485-6954-4faf-813b-1c9d25ea750c");
    private static final Instant NOW = Instant.parse("2026-09-05T12:00:00Z");
    private final CredentialService credentials = new CredentialService();

    @Test
    public void registrationConflictIncludesOnlyConflictingFields() {
        for (List<ErrorDetail> details : List.of(
                List.of(new ErrorDetail("username", "A user with this username already exists")),
                List.of(new ErrorDetail("email", "A user with this email already exists")),
                List.of(new ErrorDetail("username", "A user with this username already exists"),
                        new ErrorDetail("email", "A user with this email already exists")))) {
            final UserData repository = new UserData() {
                @Override
                public boolean addPendingUserIfAbsent(User user, String hash, Date expiresAt) {
                    return false;
                }

                @Override
                public List<ErrorDetail> registrationConflicts(String username, String email) {
                    return details;
                }
            };
            final AuthService service = new AuthService(repository, new TokenService(), credentials,
                    Clock.fixed(NOW, ZoneOffset.UTC), "http://localhost/api/v3");
            final RegisterRequest request = new RegisterRequest();
            request.setUsername("conflicting-user");
            request.setEmail("conflicting@example.test");
            request.setPassword("password123");
            try {
                service.register(request);
                fail("Duplicate registration must be rejected");
            } catch (AccountException expected) {
                assertEquals(Response.Status.CONFLICT, expected.getStatus());
                assertEquals("USER_ALREADY_EXISTS", expected.getCode());
                assertEquals(details, expected.getDetails());
            }
        }
    }

    @Test
    public void confirmationAndResendKeepSingleUseLinkSemantics() {
        final User user = user();
        user.setConfirmationCodeHash(credentials.hashOneTimeCode("original-code"));
        user.setConfirmationExpiresAt(Date.from(NOW.plusSeconds(60)));
        final AuthService service = service(user);
        final String link = service.resendConfirmation(user.getEmail(), "password123").getConfirmationUrl();
        final String code = link.substring(link.indexOf("?code=") + 6);
        assertAccountError(() -> service.confirm(USER_ID, "original-code"),
                Response.Status.BAD_REQUEST, "INVALID_CONFIRMATION_LINK");
        assertEquals(AccountStatus.ACTIVE, service.confirm(USER_ID, code).getUserStatus());
        assertAccountError(() -> service.confirm(USER_ID, code),
                Response.Status.CONFLICT, "ACCOUNT_ALREADY_CONFIRMED");
        assertAccountError(() -> service.resendConfirmation(user.getEmail(), "password123"),
                Response.Status.CONFLICT, "ACCOUNT_ALREADY_CONFIRMED");
    }

    @Test
    public void confirmationRejectsMissingUserAndPreservesBlockedStatus() {
        final User user = user();
        user.setUserStatus(AccountStatus.BLOCKED);
        user.setConfirmationCodeHash(credentials.hashOneTimeCode("valid-code"));
        user.setConfirmationExpiresAt(Date.from(NOW.plusSeconds(60)));
        final AuthService service = service(user);
        assertAccountError(() -> service.confirm(UUID.randomUUID(), "valid-code"),
                Response.Status.NOT_FOUND, "USER_NOT_FOUND");
        assertEquals(AccountStatus.BLOCKED, service.confirm(USER_ID, "valid-code").getUserStatus());
    }

    private void assertAccountError(Runnable action, Response.Status status, String code) {
        try {
            action.run();
            fail("Expected account error " + code);
        } catch (AccountException expected) {
            assertEquals(status, expected.getStatus());
            assertEquals(code, expected.getCode());
        }
    }

    @Test
    public void expiredConfirmationLinkReturnsGone() {
        final String code = "expired-code";
        final User user = user();
        user.setConfirmationCodeHash(credentials.hashOneTimeCode(code));
        user.setConfirmationExpiresAt(Date.from(NOW.minusSeconds(1)));
        final AuthService service = service(user);

        try {
            service.confirm(USER_ID, code);
            fail("Expired confirmation must be rejected");
        } catch (AccountException expected) {
            assertEquals(Response.Status.GONE, expected.getStatus());
            assertEquals("CONFIRMATION_LINK_EXPIRED", expected.getCode());
        }
    }

    @Test
    public void consumedResetLinkReturnsConflict() {
        final String code = "used-reset-code";
        final User user = user();
        user.setResetCodeHash(credentials.hashOneTimeCode(code));
        user.setResetExpiresAt(Date.from(NOW.plusSeconds(60)));
        user.setResetUsedAt(Date.from(NOW.minusSeconds(1)));
        final AuthService service = service(user);

        try {
            service.resetPassword(code, "NewSecurePass123");
            fail("Consumed reset link must be rejected");
        } catch (AccountException expected) {
            assertEquals(Response.Status.CONFLICT, expected.getStatus());
            assertEquals("RESET_LINK_ALREADY_USED", expected.getCode());
        }
    }

    @Test
    public void expiredResetLinkReturnsGone() {
        final String code = "expired-reset-code";
        final User user = user();
        user.setResetCodeHash(credentials.hashOneTimeCode(code));
        user.setResetExpiresAt(Date.from(NOW.minusSeconds(1)));
        final AuthService service = service(user);

        try {
            service.resetPassword(code, "NewSecurePass123");
            fail("Expired reset link must be rejected");
        } catch (AccountException expected) {
            assertEquals(Response.Status.GONE, expected.getStatus());
            assertEquals("RESET_LINK_EXPIRED", expected.getCode());
        }
    }

    @Test
    public void unknownResetCodeReturnsInvalidLink() {
        final User user = user();
        final AuthService service = service(user);

        try {
            service.resetPassword("unknown-reset-code", "NewSecurePass123");
            fail("Unknown reset code must be rejected");
        } catch (AccountException expected) {
            assertEquals(Response.Status.BAD_REQUEST, expected.getStatus());
            assertEquals("INVALID_RESET_LINK", expected.getCode());
        }
    }

    @Test
    public void forgotPasswordReturnsResetLinkInTrainingMode() {
        final User user = user();
        final PasswordResetLinkResponse response = service(user).forgotPassword(user.getEmail());

        assertTrue(response.getResetUrl().startsWith(
                "http://localhost/api/v3/auth/password/reset?code="));
        assertEquals(NOW.plusSeconds(30 * 60).toString(), response.getExpiresAt());
        assertNotNull(user.getResetCodeHash());
    }

    @Test
    public void forgotPasswordHidesResetLinkWhenExplicitlyDisabled() {
        final User user = user();
        final PasswordResetLinkResponse response = service(user, false).forgotPassword(user.getEmail());

        assertNull(response.getResetUrl());
        assertEquals(NOW.plusSeconds(30 * 60).toString(), response.getExpiresAt());
        assertNotNull(user.getResetCodeHash());
    }

    @Test
    public void loginGetsRateLimitedAfterFiveInvalidAttempts() {
        final User user = user();
        user.setUserStatus(AccountStatus.ACTIVE);
        final String email = user.getEmail();
        final AuthService service = service(user);

        for (int i = 0; i < 4; i++) {
            assertNull(service.login(email, "wrong-password"));
        }

        try {
            service.login(email, "wrong-password");
            fail("After 5th invalid attempt should be rate limited");
        } catch (AccountException expected) {
            assertEquals(Response.Status.TOO_MANY_REQUESTS, expected.getStatus());
            assertEquals("LOGIN_RATE_LIMITED", expected.getCode());
        }
    }

    @Test
    public void loginSuccessfullyResetsRateLimit() {
        final User user = user();
        user.setUserStatus(AccountStatus.ACTIVE);
        final String email = user.getEmail();
        final AuthService service = service(user);

        for (int i = 0; i < 4; i++) {
            assertNull(service.login(email, "wrong-password"));
        }

        assertNotNull(service.login(email, "password123"));
        assertNull(service.login(email, "wrong-password"));
    }

    @Test
    public void resendConfirmationUsesTheSameRateLimitAsLogin() {
        final User user = user();
        final AuthService service = service(user);

        for (int i = 0; i < 4; i++) {
            assertNull(service.login(user.getEmail(), "wrong-password"));
        }

        try {
            service.resendConfirmation(user.getEmail(), "wrong-password");
            fail("Confirmation resend must not bypass the authentication rate limit");
        } catch (AccountException expected) {
            assertEquals(Response.Status.TOO_MANY_REQUESTS, expected.getStatus());
            assertEquals("LOGIN_RATE_LIMITED", expected.getCode());
        }
    }

    @Test
    public void successfulPasswordResetClearsTheLoginLock() {
        final String code = "valid-reset-code";
        final User user = user();
        user.setUserStatus(AccountStatus.ACTIVE);
        user.setResetCodeHash(credentials.hashOneTimeCode(code));
        user.setResetExpiresAt(Date.from(NOW.plusSeconds(60)));
        final AuthService service = service(user);

        for (int i = 0; i < 4; i++) {
            assertNull(service.login(user.getEmail(), "wrong-password"));
        }
        try {
            service.login(user.getEmail(), "wrong-password");
            fail("The account identifier must be locked after five failures");
        } catch (AccountException expected) {
            assertEquals("LOGIN_RATE_LIMITED", expected.getCode());
        }

        service.resetPassword(code, "NewSecurePass123");
        assertNotNull(service.login(user.getEmail(), "NewSecurePass123"));
    }

    private AuthService service(final User user) {
        return service(user, true);
    }

    private AuthService service(final User user, final boolean exposeTestLinks) {
        final UserData repository = new UserData() {
            @Override
            public User confirmUser(UUID id, Consumer<User> validate) {
                final User current = findUserById(id);
                validate.accept(current);
                current.setConfirmedAt(Date.from(NOW));
                current.setConfirmationExpiresAt(null);
                if (current.getUserStatus() != AccountStatus.BLOCKED) {
                    current.setUserStatus(AccountStatus.ACTIVE);
                }
                return current;
            }

            @Override
            public User setConfirmationLink(UUID id, String hash, Date expiresAt, Consumer<User> validate) {
                final User current = findUserById(id);
                validate.accept(current);
                current.setConfirmationCodeHash(hash);
                current.setConfirmationExpiresAt(expiresAt);
                return current;
            }

            @Override
            public User findUserById(UUID id) {
                return USER_ID.equals(id) ? user : null;
            }

            @Override
            public User findUserByName(final String username) {
                return user.getUsername().equals(username) ? user : null;
            }

            @Override
            public User findUserByEmail(final String email) {
                return user.getEmail().equalsIgnoreCase(email) ? user : null;
            }

            @Override
            public User findUserByResetCodeHash(final String resetCodeHash) {
                return resetCodeHash != null && resetCodeHash.equals(user.getResetCodeHash()) ? user : null;
            }

            @Override
            public User setResetLink(final UUID userId, final String hash, final Date expiresAt) {
                if (!USER_ID.equals(userId)) {
                    return null;
                }
                user.setResetCodeHash(hash);
                user.setResetExpiresAt(expiresAt);
                user.setResetUsedAt(null);
                return user;
            }

            @Override
            public boolean replacePasswordIfCurrent(final String username, final String currentPassword,
                    final String passwordHash) {
                if (!user.getUsername().equals(username) || !credentials.passwordMatches(currentPassword, user.getPassword())) {
                    return false;
                }
                user.setPassword(passwordHash);
                return true;
            }

            @Override
            public User resetPassword(final UUID userId, final String expectedHash, final String passwordHash) {
                if (!USER_ID.equals(userId) || !expectedHash.equals(user.getResetCodeHash())
                        || user.getResetUsedAt() != null) {
                    return null;
                }
                user.setPassword(passwordHash);
                user.setResetUsedAt(Date.from(NOW));
                user.setResetExpiresAt(null);
                user.setTokenVersion(user.getTokenVersion() + 1);
                return user;
            }
        };
        return new AuthService(repository, new TokenService(), credentials,
                Clock.fixed(NOW, ZoneOffset.UTC), "http://localhost/api/v3", exposeTestLinks);
    }

    private User user() {
        return UserData.createUser(USER_ID, "user1", "Test", "User", "test@example.com",
                "password123", null, AccountStatus.PENDING, Role.USER);
    }
}
