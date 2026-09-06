package io.swagger.petstore.service;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertTrue;

public class CredentialServiceTest {
    private final CredentialService service = new CredentialService();

    @Test
    public void bcryptPasswordCanBeVerified() {
        final String hash = service.hashPassword("SecurePass123");
        assertTrue(service.isBcrypt(hash));
        assertTrue(service.passwordMatches("SecurePass123", hash));
        assertFalse(service.passwordMatches("wrong-password", hash));
    }

    @Test
    public void oneTimeCodesAreRandomAndComparedByHash() {
        final String first = service.newOneTimeCode();
        final String second = service.newOneTimeCode();
        assertNotEquals(first, second);
        assertTrue(service.codeMatches(first, service.hashOneTimeCode(first)));
        assertFalse(service.codeMatches(second, service.hashOneTimeCode(first)));
    }
}
