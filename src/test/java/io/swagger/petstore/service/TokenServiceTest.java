package io.swagger.petstore.service;

import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;
import java.util.UUID;

public class TokenServiceTest {
    private final TokenService tokenService = new TokenService();
    private final User user = testUser();

    private static User testUser() {
        final User value = new User();
        value.setId(UUID.fromString("b9ec3485-6954-4faf-813b-1c9d25ea750c"));
        value.setUsername("user1");
        value.setRole(Role.USER);
        value.setTokenVersion(7);
        return value;
    }

    @Test
    public void issuedTokenCanBeValidated() throws Exception {
        final String token = tokenService.issueToken(user);
        final TokenService.TokenClaims claims = tokenService.validate(token);
        assertEquals("user1", claims.getUsername());
        assertEquals(user.getRole(), claims.getRole());
        assertEquals(7, claims.getTokenVersion());
    }

    @Test
    public void modifiedTokenIsRejected() throws Exception {
        final String token = tokenService.issueToken(user);
        final int signatureStart = token.lastIndexOf('.') + 1;
        final char firstSignatureCharacter = token.charAt(signatureStart);
        final char replacement = firstSignatureCharacter == 'A' ? 'B' : 'A';
        final String modified = token.substring(0, signatureStart) + replacement
                + token.substring(signatureStart + 1);
        try {
            tokenService.validate(modified);
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
