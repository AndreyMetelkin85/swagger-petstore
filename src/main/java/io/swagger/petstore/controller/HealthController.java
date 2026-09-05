package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.data.Database;
import io.swagger.petstore.model.HealthResponse;
import io.swagger.petstore.utils.Util;

import java.util.Date;

public class HealthController {
    public ResponseContext health(final RequestContext request) {
        final boolean databaseUp = Database.isHealthy();
        return new ResponseContext()
                .status(databaseUp ? 200 : 503)
                .contentType(Util.getMediaType(request))
                .entity(new HealthResponse(databaseUp ? "UP" : "DOWN", "swagger-petstore",
                        databaseUp ? "UP" : "DOWN", new Date()));
    }
}
