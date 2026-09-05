package io.swagger.petstore.service;

import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

public class TokenServiceTest {
    private final TokenService tokenService = new TokenService();
    private final User user = testUser();

    private static User testUser() {
        final User value = new User();
        value.setId(2);
        value.setUsername("user1");
        value.setRole(Role.USER);
        return value;
    }

    @Test
    public void issuedTokenCanBeValidated() throws Exception {
        final String token = tokenService.issueToken(user);
        final TokenService.TokenClaims claims = tokenService.validate(token);
        assertEquals("user1", claims.getUsername());
        assertEquals(user.getRole(), claims.getRole());
    }

    @Test
    public void modifiedTokenIsRejected() throws Exception {
        final String token = tokenService.issueToken(user);
        try {
            tokenService.validate(token.substring(0, token.length() - 1) + "x");
            fail("Modified token must be rejected");
        } catch (TokenException expected) {
            assertEquals("INVALID_TOKEN", expected.getCode());
        }
    }

    @Test
    public void expiredTokenIsRejected() throws Exception {
        final String token = tokenService.issueToken(user, 0);
        try {
            tokenService.validate(token);
            fail("Expired token must be rejected");
        } catch (TokenException expected) {
            assertEquals("TOKEN_EXPIRED", expected.getCode());
        }
    }
}
