package io.swagger.petstore.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.model.User;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;

/** Minimal HS256 JWT implementation suitable for a local training service. */
public class TokenService {
    public static final long DEFAULT_TTL_SECONDS = 3600L;
    private static final String ALGORITHM = "HmacSHA256";
    private static final int MIN_SECRET_BYTES = 32;
    private static final String INSECURE_LEGACY_SECRET = "local-petstore-secret-change-me";
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final byte[] PROCESS_SECRET = loadProcessSecret();

    private final byte[] secret;

    public TokenService() {
        this.secret = PROCESS_SECRET.clone();
    }

    TokenService(final String configuredSecret) {
        this.secret = validatedSecret(configuredSecret);
    }

    public String issueToken(final User user) {
        return issueToken(user, DEFAULT_TTL_SECONDS);
    }

    public String issueToken(final User user, final long ttlSeconds) {
        try {
            final long now = System.currentTimeMillis() / 1000L;
            final Map<String, Object> header = new LinkedHashMap<>();
            header.put("alg", "HS256");
            header.put("typ", "JWT");

            final Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("sub", user.getUsername());
            payload.put("role", user.getRole().name());
            payload.put("ver", user.getTokenVersion());
            payload.put("iat", now);
            payload.put("exp", now + ttlSeconds);

            final String encodedHeader = encode(MAPPER.writeValueAsBytes(header));
            final String encodedPayload = encode(MAPPER.writeValueAsBytes(payload));
            final String unsigned = encodedHeader + "." + encodedPayload;
            return unsigned + "." + encode(sign(unsigned));
        } catch (Exception exception) {
            throw new IllegalStateException("Could not issue access token", exception);
        }
    }

    public TokenClaims validate(final String token) throws TokenException {
        try {
            final String[] parts = token == null ? new String[0] : token.split("\\.");
            if (parts.length != 3) {
                throw new TokenException("INVALID_TOKEN", "Access token is invalid");
            }

            final String unsigned = parts[0] + "." + parts[1];
            final byte[] actualSignature = Base64.getUrlDecoder().decode(parts[2]);
            if (!MessageDigest.isEqual(sign(unsigned), actualSignature)) {
                throw new TokenException("INVALID_TOKEN", "Access token is invalid");
            }

            final Map<String, Object> payload = MAPPER.readValue(
                    Base64.getUrlDecoder().decode(parts[1]),
                    new TypeReference<Map<String, Object>>() { });
            final String username = String.valueOf(payload.get("sub"));
            final Role role = Role.valueOf(String.valueOf(payload.get("role")));
            final int tokenVersion = ((Number) payload.get("ver")).intValue();
            final long expiresAt = ((Number) payload.get("exp")).longValue();
            if (expiresAt <= System.currentTimeMillis() / 1000L) {
                throw new TokenException("TOKEN_EXPIRED", "Access token has expired");
            }
            return new TokenClaims(username, role, tokenVersion, expiresAt);
        } catch (TokenException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new TokenException("INVALID_TOKEN", "Access token is invalid");
        }
    }

    private byte[] sign(final String value) throws Exception {
        final Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(secret, ALGORITHM));
        return mac.doFinal(value.getBytes(StandardCharsets.UTF_8));
    }

    private String encode(final byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    private static byte[] loadProcessSecret() {
        final String configured = System.getenv("PETSTORE_TOKEN_SECRET");
        if (configured == null || configured.trim().isEmpty()) {
            final byte[] generated = new byte[MIN_SECRET_BYTES];
            new SecureRandom().nextBytes(generated);
            return generated;
        }
        return validatedSecret(configured);
    }

    private static byte[] validatedSecret(final String value) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("JWT secret must not be empty");
        }
        if (INSECURE_LEGACY_SECRET.equals(value)) {
            throw new IllegalArgumentException("The legacy JWT secret is not allowed");
        }
        final byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        if (bytes.length < MIN_SECRET_BYTES) {
            throw new IllegalArgumentException("JWT secret must contain at least 32 UTF-8 bytes");
        }
        return bytes;
    }

    public static final class TokenClaims {
        private final String username;
        private final Role role;
        private final int tokenVersion;
        private final long expiresAt;

        TokenClaims(String username, Role role, int tokenVersion, long expiresAt) {
            this.username = username;
            this.role = role;
            this.tokenVersion = tokenVersion;
            this.expiresAt = expiresAt;
        }

        public String getUsername() {
            return username;
        }

        public Role getRole() {
            return role;
        }

        public int getTokenVersion() {
            return tokenVersion;
        }

        public long getExpiresAt() {
            return expiresAt;
        }
    }
}
