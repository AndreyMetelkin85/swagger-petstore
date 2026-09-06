package io.swagger.petstore.model;

import java.util.ArrayList;
import java.util.List;

public class ErrorResponse {
    private int status;
    private String error;
    private String message;
    private List<ErrorDetail> details = new ArrayList<>();

    public ErrorResponse() {
    }

    public ErrorResponse(int status, String error, String message) {
        this.status = status;
        this.error = error;
        this.message = message;
    }

    public ErrorResponse(int status, String error, String message, List<ErrorDetail> details) {
        this.status = status;
        this.error = error;
        this.message = message;
        if (details != null) {
            this.details = details;
        }
    }

    public int getStatus() {
        return status;
    }

    public void setStatus(int status) {
        this.status = status;
    }

    public String getError() {
        return error;
    }

    public void setError(String error) {
        this.error = error;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public List<ErrorDetail> getDetails() {
        return details;
    }

    public void setDetails(List<ErrorDetail> details) {
        this.details = details;
    }
}
