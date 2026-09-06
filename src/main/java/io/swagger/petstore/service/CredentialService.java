package io.swagger.petstore.service;

import org.mindrot.jbcrypt.BCrypt;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public class CredentialService {
    private static final int BCRYPT_COST = 10;
    private static final SecureRandom RANDOM = new SecureRandom();

    public String hashPassword(String password) {
        return BCrypt.hashpw(password, BCrypt.gensalt(BCRYPT_COST));
    }

    public boolean passwordMatches(String password, String storedPassword) {
        if (password == null || storedPassword == null) {
            return false;
        }
        if (isBcrypt(storedPassword)) {
            try {
                return BCrypt.checkpw(password, storedPassword);
            } catch (IllegalArgumentException ignored) {
                return false;
            }
        }
        return MessageDigest.isEqual(password.getBytes(StandardCharsets.UTF_8),
                storedPassword.getBytes(StandardCharsets.UTF_8));
    }

    public boolean isBcrypt(String value) {
        return value != null && (value.startsWith("$2a$") || value.startsWith("$2b$")
                || value.startsWith("$2y$"));
    }

    public String newOneTimeCode() {
        final byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public String hashOneTimeCode(String code) {
        if (code == null) {
            return null;
        }
        try {
            final byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(code.getBytes(StandardCharsets.UTF_8));
            final StringBuilder result = new StringBuilder(digest.length * 2);
            for (byte value : digest) {
                result.append(String.format("%02x", value & 0xff));
            }
            return result.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    public boolean codeMatches(String code, String storedHash) {
        final String actual = hashOneTimeCode(code);
        return actual != null && storedHash != null && MessageDigest.isEqual(
                actual.getBytes(StandardCharsets.US_ASCII),
                storedHash.getBytes(StandardCharsets.US_ASCII));
    }
}
