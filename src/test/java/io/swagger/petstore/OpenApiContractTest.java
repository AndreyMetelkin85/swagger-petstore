package io.swagger.petstore;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.examples.Example;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.parser.OpenAPIV3Parser;
import io.swagger.v3.parser.core.models.ParseOptions;
import io.swagger.v3.parser.core.models.SwaggerParseResult;
import org.junit.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public class OpenApiContractTest {
    private static final String SOURCE_PATH = "src/main/resources/openapi.yaml";
    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    public void openApiDocumentIsValidAndHasExpectedPublicShape() throws Exception {
        final ParsedContract contract = parseContract();
        final OpenAPI openAPI = contract.openAPI;

        assertEquals("3.0.4", openAPI.getOpenapi());
        assertEquals("Swagger Petstore API", openAPI.getInfo().getTitle());
        assertEquals("API зоомагазина, в котором пользователи могут регистрироваться, просматривать питомцев "
                        + "и оформлять заказы.\nПроект предназначен для практики ручного и автоматизированного "
                        + "тестирования на реалистичных сценариях успешной работы и обработки ошибок.",
                openAPI.getInfo().getDescription());
        assertEquals(Arrays.asList("Health", "Registration", "Authentication", "Pets", "Orders",
                        "Users", "Administration"),
                openAPI.getTags().stream().map(tag -> tag.getName()).collect(Collectors.toList()));

        assertNotNull(openAPI.getPaths().get("/auth/login"));
        assertNotNull(openAPI.getPaths().get("/auth/confirm/{userId}"));
        assertNotNull(openAPI.getPaths().get("/auth/confirmation/resend"));
        assertNotNull(openAPI.getPaths().get("/auth/password/forgot"));
        assertNotNull(openAPI.getPaths().get("/auth/password/reset/{userId}"));
        assertNotNull(openAPI.getPaths().get("/admin/users/{userId}/block"));
        assertNotNull(openAPI.getPaths().get("/admin/users/{userId}/unblock"));
        assertNotNull(openAPI.getPaths().get("/user/me"));
        assertNotNull(openAPI.getPaths().get("/store/order/{orderId}/approve"));
        assertNotNull(openAPI.getPaths().get("/store/order/{orderId}/ship"));
        assertNotNull(openAPI.getPaths().get("/store/order/{orderId}/deliver"));
        assertNotNull(openAPI.getPaths().get("/store/order/{orderId}/cancel"));
        assertNotNull(openAPI.getComponents().getSecuritySchemes().get("bearerAuth"));
        assertNull(openAPI.getPaths().get("/user/me").getDelete());
        assertNull(openAPI.getPaths().get("/user/{username}").getDelete());
        assertNull(openAPI.getPaths().get("/store/order/{orderId}").getDelete());
        assertEquals(Collections.emptyList(), openAPI.getPaths().get("/health").getGet().getSecurity());

        assertEquals("RegistrationController", extension(openAPI.getPaths().get("/auth/register").getPost()));
        assertEquals("RegistrationController", extension(openAPI.getPaths().get("/auth/confirm/{userId}").getGet()));
        assertEquals("AuthenticationController", extension(openAPI.getPaths().get("/auth/login").getPost()));
        assertEquals("AuthenticationController", extension(openAPI.getPaths().get("/auth/password/forgot").getPost()));

        assertNull("Concrete reusable responses must not leak examples between endpoints",
                openAPI.getComponents().getResponses());
        assertEquals(new HashSet<>(Arrays.asList("status", "error", "message", "details")),
                new HashSet<>(openAPI.getComponents().getSchemas().get("ErrorResponse").getRequired()));
        assertNull(openAPI.getComponents().getSchemas().get("ErrorResponse").getProperties().get("code"));
        assertNull(openAPI.getComponents().getSchemas().get("ValidationErrorResponse"));
        assertNull(openAPI.getComponents().getSchemas().get("NotFoundErrorResponse"));
    }

    @Test
    public void schemasUseUuidStatusEnumAndSnakeCaseLoginResponse() throws Exception {
        final OpenAPI openAPI = parseContract().openAPI;

        assertEquals("uuid", property(openAPI, "User", "id").getFormat());
        assertEquals("uuid", property(openAPI, "Pet", "id").getFormat());
        assertEquals("uuid", property(openAPI, "Order", "id").getFormat());
        assertEquals("uuid", property(openAPI, "Order", "petId").getFormat());
        assertEquals(Arrays.asList("available", "pending", "reserved", "sold"),
                property(openAPI, "Pet", "status").getEnum());
        assertEquals(Arrays.asList("placed", "approved", "shipped", "delivered", "cancelled"),
                property(openAPI, "Order", "status").getEnum());
        assertEquals(Arrays.asList("PENDING", "ACTIVE", "BLOCKED"),
                openAPI.getComponents().getSchemas().get("AccountStatus").getEnum());
        assertNotNull(property(openAPI, "User", "userStatus").get$ref());
        assertTrue(openAPI.getComponents().getSchemas().get("User").getRequired().contains("userStatus"));

        final Schema login = openAPI.getComponents().getSchemas().get("LoginResponse");
        assertEquals(new HashSet<>(Arrays.asList("access_token", "token_type", "expires_in", "user")),
                new HashSet<>(login.getRequired()));
        assertTrue(login.getProperties().containsKey("access_token"));
        assertTrue(login.getProperties().containsKey("token_type"));
        assertTrue(login.getProperties().containsKey("expires_in"));
        assertFalse(login.getProperties().containsKey("accessToken"));
        assertFalse(login.getProperties().containsKey("tokenType"));
        assertFalse(login.getProperties().containsKey("expiresIn"));
        assertTrue(parseContract().source.contains("Authorization: Bearer <access_token>"));
        assertFalse(parseContract().source.contains("Bearer access token"));

        final Schema petCreate = openAPI.getComponents().getSchemas().get("PetCreateRequest");
        final Schema petUpdate = openAPI.getComponents().getSchemas().get("PetUpdateRequest");
        final Schema orderCreate = openAPI.getComponents().getSchemas().get("OrderCreateRequest");
        assertEquals(Collections.singletonList("name"), petCreate.getRequired());
        assertFalse(petCreate.getProperties().containsKey("id"));
        assertTrue(petUpdate.getRequired().containsAll(Arrays.asList("id", "name", "version")));
        assertTrue(openAPI.getComponents().getSchemas().get("Pet").getRequired().contains("version"));
        assertEquals(new HashSet<>(Arrays.asList("petId", "quantity")),
                new HashSet<>(orderCreate.getRequired()));
        assertFalse(orderCreate.getProperties().containsKey("id"));
        assertFalse(orderCreate.getProperties().containsKey("status"));
        assertFalse(orderCreate.getProperties().containsKey("complete"));
    }

    @Test
    public void operationDescriptionsAreShortAndHumanReadable() throws Exception {
        final OpenAPI openAPI = parseContract().openAPI;

        openAPI.getTags().forEach(tag -> {
            assertNotNull("Missing description for tag " + tag.getName(), tag.getDescription());
            assertTrue("Tag description must be in Russian: " + tag.getName(),
                    tag.getDescription().matches("(?s).*[А-Яа-яЁё].*"));
        });
        openAPI.getPaths().forEach((path, pathItem) ->
                pathItem.readOperationsMap().forEach((method, operation) -> {
                    final String location = method + " " + path;
                    final String description = operation.getDescription();
                    assertNotNull("Missing endpoint description: " + location, description);
                    assertTrue("Endpoint description must be in Russian: " + location,
                            description.matches("(?s).*[А-Яа-яЁё].*"));
                    assertTrue("Endpoint description is too long: " + location,
                            description.length() <= 160);
                    for (String implementationDetail
                            : Arrays.asList("HS256", "JWT", "Authorization:", "локальн", "`")) {
                        assertFalse("Implementation detail in endpoint description: " + location,
                                description.contains(implementationDetail));
                    }
                }));
        assertEquals("Проверяет учётные данные и возвращает Bearer token.",
                openAPI.getPaths().get("/auth/login").getPost().getDescription());
    }

    @Test
    public void everyDomainDocumentsItsOwnErrorCodes() throws Exception {
        final OpenAPI openAPI = parseContract().openAPI;

        assertErrorCodes(openAPI.getPaths().get("/auth/register").getPost(), "409",
                "USER_ALREADY_EXISTS");
        assertErrorCodes(openAPI.getPaths().get("/auth/login").getPost(), "403",
                "ACCOUNT_NOT_VERIFIED", "ACCOUNT_BLOCKED");
        assertErrorCodes(openAPI.getPaths().get("/auth/password/reset/{userId}").getPost(), "409",
                "RESET_LINK_ALREADY_USED", "RESET_STATE_CHANGED");
        assertErrorCodes(openAPI.getPaths().get("/pet/{petId}").getGet(), "404", "PET_NOT_FOUND");
        assertErrorCodes(openAPI.getPaths().get("/store/order/{orderId}").getGet(), "404",
                "ORDER_NOT_FOUND");
        assertErrorCodes(openAPI.getPaths().get("/store/order").getPost(), "404",
                "PET_NOT_FOUND");
        assertErrorCodes(openAPI.getPaths().get("/store/order").getPost(), "409",
                "PET_NOT_AVAILABLE");
        assertErrorCodes(openAPI.getPaths().get("/store/order/{orderId}/approve").getPost(), "409",
                "INVALID_STATUS_TRANSITION");
        assertErrorCodes(openAPI.getPaths().get("/store/order/{orderId}/cancel").getPost(), "403",
                "ORDER_ACCESS_DENIED", "ACCOUNT_NOT_VERIFIED", "ACCOUNT_BLOCKED");
        assertErrorCodes(openAPI.getPaths().get("/pet/{petId}").getDelete(), "409",
                "PET_HAS_ORDERS");
        assertErrorCodes(openAPI.getPaths().get("/pet").getPut(), "409",
                "PET_HAS_ACTIVE_ORDER", "PET_VERSION_CONFLICT");
        assertErrorCodes(openAPI.getPaths().get("/user/{username}").getGet(), "404",
                "USER_NOT_FOUND");
        assertErrorCodes(openAPI.getPaths().get("/admin/users/{userId}/block").getPost(), "403",
                "FORBIDDEN", "ACCOUNT_NOT_VERIFIED", "ACCOUNT_BLOCKED", "ADMIN_ACCOUNT_PROTECTED");
        assertErrorCodes(openAPI.getPaths().get("/admin/users/{userId}/block").getPost(), "404",
                "USER_NOT_FOUND");
        assertErrorCodes(openAPI.getPaths().get("/admin/users/{userId}/block").getPost(), "409",
                "INVALID_STATUS_TRANSITION");
    }

    @Test
    public void endpointStatusErrorCodeExamplesUseThePublicContract() throws Exception {
        final OpenAPI openAPI = parseContract().openAPI;

        for (Map.Entry<String, PathItem> path : openAPI.getPaths().entrySet()) {
            for (Map.Entry<PathItem.HttpMethod, Operation> operation
                    : path.getValue().readOperationsMap().entrySet()) {
                for (Map.Entry<String, ApiResponse> response
                        : operation.getValue().getResponses().entrySet()) {
                    if (!response.getKey().matches("[45]\\d\\d")) {
                        continue;
                    }
                    final MediaType mediaType = response.getValue().getContent() == null
                            ? null : response.getValue().getContent().get("application/json");
                    if (mediaType == null || mediaType.getSchema() == null
                            || !"#/components/schemas/ErrorResponse".equals(mediaType.getSchema().get$ref())) {
                        continue;
                    }
                    final String location = operation.getKey() + " " + path.getKey()
                            + " -> " + response.getKey();
                    assertNotNull("Named error examples are required for " + location,
                            mediaType.getExamples());
                    assertFalse("Named error examples are required for " + location,
                            mediaType.getExamples().isEmpty());
                    for (Example example : mediaType.getExamples().values()) {
                        final Map value = example.getValue() instanceof Map
                                ? (Map) example.getValue()
                                : JSON.convertValue(example.getValue(), Map.class);
                        assertEquals(location, Integer.parseInt(response.getKey()), value.get("status"));
                        assertTrue(location, value.get("error") instanceof String
                                && !((String) value.get("error")).isEmpty());
                        assertTrue(location, value.get("message") instanceof String
                                && !((String) value.get("message")).isEmpty());
                        assertTrue(location, value.get("details") instanceof java.util.List);
                        final String code = String.valueOf(value.get("error"));
                        if (code.startsWith("PET_")) {
                            assertTrue(location, path.getKey().startsWith("/pet")
                                    || path.getKey().equals("/store/order"));
                        }
                        if (code.startsWith("ORDER_")) {
                            assertTrue(location, path.getKey().startsWith("/store/order"));
                        }
                        if (code.equals("ADMIN_ACCOUNT_PROTECTED")) {
                            assertTrue(location, path.getKey().startsWith("/admin/users"));
                        }
                    }
                }
            }
        }
    }

    @Test
    public void realisticUuidExamplesReplacePatternedPlaceholders() throws Exception {
        final String source = parseContract().source;
        assertTrue(source.contains("b9ec3485-6954-4faf-813b-1c9d25ea750c"));
        assertTrue(source.contains("7c1d1b70-f31e-42cd-9f78-6a5d87ed8620"));
        assertTrue(source.contains("e3a724f6-580d-4d87-91c4-8f17e2027629"));
        assertTrue(source.contains("0e446653-3b7b-4ad1-81d3-b0a71af26f31"));
        assertTrue(source.contains("f0c2308f-19f2-4689-a395-7926a5825cd0"));
        assertFalse(source.contains("22222222-2222-4222-8222-222222222222"));
        assertFalse(source.contains("44444444-4444-4444-8444-444444444444"));
        assertFalse(source.contains("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"));
    }

    @Test
    public void legacyOperationsStayHiddenFromSwagger() throws Exception {
        final OpenAPI openAPI = parseContract().openAPI;
        assertNull(openAPI.getPaths().get("/user"));
        assertNull(openAPI.getPaths().get("/user/login"));
        assertNull(openAPI.getPaths().get("/user/logout"));
        assertNull(openAPI.getPaths().get("/user/createWithList"));
        assertNull(openAPI.getPaths().get("/pet/{petId}/uploadImage"));
        assertNull(openAPI.getPaths().get("/pet/{petId}").getPost());
        assertNull(openAPI.getPaths().get("/user/{username}").getPut());
        assertNull(openAPI.getPaths().get("/user/me").getDelete());
        assertNull(openAPI.getPaths().get("/user/{username}").getDelete());
        assertNull(openAPI.getPaths().get("/store/order/{orderId}").getDelete());
    }

    private static String extension(Operation operation) {
        return String.valueOf(operation.getExtensions().get("x-swagger-router-controller"));
    }

    private static Schema property(OpenAPI openAPI, String schema, String property) {
        return (Schema) openAPI.getComponents().getSchemas().get(schema).getProperties().get(property);
    }

    private static void assertErrorCodes(Operation operation, String status, String... expectedCodes) {
        final ApiResponse response = operation.getResponses().get(status);
        assertNotNull("Missing response " + status, response);
        final MediaType mediaType = response.getContent().get("application/json");
        assertNotNull("Missing application/json for " + status, mediaType);
        assertNotNull("Named examples are required for " + status, mediaType.getExamples());
        final Set<String> actualCodes = new LinkedHashSet<>();
        for (Example example : mediaType.getExamples().values()) {
            final Object value = example.getValue();
            assertNotNull("Error example value is required", value);
            final Map parsed = value instanceof Map ? (Map) value : JSON.convertValue(value, Map.class);
            actualCodes.add(String.valueOf(parsed.get("error")));
        }
        assertEquals(new LinkedHashSet<>(Arrays.asList(expectedCodes)), actualCodes);
    }

    private static ParsedContract parseContract() throws Exception {
        final String source = new String(Files.readAllBytes(Paths.get(SOURCE_PATH)), StandardCharsets.UTF_8);
        final ParseOptions options = new ParseOptions();
        options.setResolve(true);
        final SwaggerParseResult result = new OpenAPIV3Parser().readContents(source, null, options);
        assertNotNull("OpenAPI parser returned no document: " + result.getMessages(), result.getOpenAPI());
        assertTrue("OpenAPI validation messages: " + result.getMessages(),
                result.getMessages() == null || result.getMessages().isEmpty());
        return new ParsedContract(source, result.getOpenAPI());
    }

    private static final class ParsedContract {
        private final String source;
        private final OpenAPI openAPI;

        private ParsedContract(String source, OpenAPI openAPI) {
            this.source = source;
            this.openAPI = openAPI;
        }
    }
}
