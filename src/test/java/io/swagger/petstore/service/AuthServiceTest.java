package io.swagger.petstore.service;

import io.swagger.petstore.data.UserData;
import io.swagger.petstore.model.AccountStatus;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;
import org.junit.Test;

import javax.ws.rs.core.Response;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Date;
import java.util.UUID;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

public class AuthServiceTest {
    private static final UUID USER_ID = UUID.fromString("b9ec3485-6954-4faf-813b-1c9d25ea750c");
    private static final Instant NOW = Instant.parse("2026-09-05T12:00:00Z");
    private final CredentialService credentials = new CredentialService();

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
            service.resetPassword(USER_ID, code, "NewSecurePass123");
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
            service.resetPassword(USER_ID, code, "NewSecurePass123");
            fail("Expired reset link must be rejected");
        } catch (AccountException expected) {
            assertEquals(Response.Status.GONE, expected.getStatus());
            assertEquals("RESET_LINK_EXPIRED", expected.getCode());
        }
    }

    private AuthService service(final User user) {
        final UserData repository = new UserData() {
            @Override
            public User findUserById(UUID id) {
                return USER_ID.equals(id) ? user : null;
            }
        };
        return new AuthService(repository, new TokenService(), credentials,
                Clock.fixed(NOW, ZoneOffset.UTC), "http://localhost/api/v3");
    }

    private User user() {
        return UserData.createUser(USER_ID, "user1", "Test", "User", "test@example.com",
                "password123", null, AccountStatus.PENDING, Role.USER);
    }
}
