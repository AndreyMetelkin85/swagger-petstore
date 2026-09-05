package io.swagger.petstore.model;

import java.util.Date;

public class HealthResponse {
    private String status;
    private String service;
    private String database;
    private Date timestamp;

    public HealthResponse() {
    }

    public HealthResponse(String status, String service, String database, Date timestamp) {
        this.status = status;
        this.service = service;
        this.database = database;
        this.timestamp = timestamp;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getService() {
        return service;
    }

    public void setService(String service) {
        this.service = service;
    }

    public String getDatabase() {
        return database;
    }

    public void setDatabase(String database) {
        this.database = database;
    }

    public Date getTimestamp() {
        return timestamp;
    }

    public void setTimestamp(Date timestamp) {
        this.timestamp = timestamp;
    }
}
