package io.swagger.petstore;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.parser.OpenAPIV3Parser;
import io.swagger.v3.parser.core.models.ParseOptions;
import io.swagger.v3.parser.core.models.SwaggerParseResult;
import org.junit.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Collections;
import java.util.Arrays;
import java.util.HashSet;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public class OpenApiContractTest {
    @Test
    public void openApiDocumentIsValidAndContainsBearerSecurity() throws Exception {
        final String source = new String(Files.readAllBytes(
                Paths.get("src/main/resources/openapi.yaml")), StandardCharsets.UTF_8);
        final ParseOptions options = new ParseOptions();
        options.setResolve(true);

        final SwaggerParseResult result = new OpenAPIV3Parser().readContents(source, null, options);
        final OpenAPI openAPI = result.getOpenAPI();

        assertNotNull("OpenAPI parser returned no document: " + result.getMessages(), openAPI);
        assertTrue("OpenAPI validation messages: " + result.getMessages(),
                result.getMessages() == null || result.getMessages().isEmpty());
        assertEquals("3.0.4", openAPI.getOpenapi());
        assertNotNull(openAPI.getPaths().get("/auth/login"));
        assertNotNull(openAPI.getPaths().get("/user/me"));
        assertNotNull(openAPI.getComponents().getSecuritySchemes().get("bearerAuth"));
        assertNotNull(openAPI.getComponents().getSchemas().get("ValidationErrorResponse"));
        assertEquals(new HashSet<>(Arrays.asList("status", "error", "message", "details")),
                new HashSet<>(openAPI.getComponents().getSchemas().get("ErrorResponse").getRequired()));
        assertNull(openAPI.getComponents().getSchemas().get("ErrorResponse")
                .getProperties().get("code"));
        assertEquals(Collections.emptyList(),
                openAPI.getPaths().get("/health").getGet().getSecurity());

        assertNull("Устаревший POST /user не должен отображаться в Swagger UI",
                openAPI.getPaths().get("/user"));
        assertNull("Устаревший /user/login не должен отображаться в Swagger UI",
                openAPI.getPaths().get("/user/login"));
        assertNull("Устаревший /user/logout не должен отображаться в Swagger UI",
                openAPI.getPaths().get("/user/logout"));
        assertNull("Устаревший /user/createWithList не должен отображаться в Swagger UI",
                openAPI.getPaths().get("/user/createWithList"));
        assertNull("Устаревший uploadImage не должен отображаться в Swagger UI",
                openAPI.getPaths().get("/pet/{petId}/uploadImage"));
        assertNull("Устаревший POST /pet/{petId} не должен отображаться в Swagger UI",
                openAPI.getPaths().get("/pet/{petId}").getPost());
        assertNull("Устаревший PUT /user/{username} не должен отображаться в Swagger UI",
                openAPI.getPaths().get("/user/{username}").getPut());
    }
}
