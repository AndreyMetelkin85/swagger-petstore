package io.swagger.petstore.utils;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class PetstoreExceptionMapperTest {
    @Test
    public void mapsInflectorInputFailuresToEndpointSpecificErrors() {
        assertIdentity("BAD_REQUEST", "Pet id must be a valid UUID",
                "Input error: couldn't convert `bad` to UUID", "/api/v3/pet/bad");
        assertIdentity("BAD_REQUEST", "Order id must be a valid UUID",
                "Input error: couldn't convert `bad` to UUID", "/api/v3/store/order/bad");
        assertIdentity("BAD_REQUEST", "Status is required",
                "Input error: missing required query parameter `status`", "/api/v3/pet/findByStatus");
        assertIdentity("BAD_REQUEST", "Request body contains malformed or incompatible JSON",
                "Input error: unable to convert input to LoginRequest", "/api/v3/auth/login");
    }

    private void assertIdentity(String error, String message, String source, String path) {
        final PetstoreExceptionMapper.ErrorIdentity identity =
                PetstoreExceptionMapper.identity(400, source, path);
        assertEquals(error, identity.getError());
        assertEquals(message, identity.getMessage());
    }
}
