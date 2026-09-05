package io.swagger.petstore.model;

import java.util.ArrayList;
import java.util.List;

public class ErrorResponse {
    private String code;
    private String message;
    private List<ErrorDetail> details = new ArrayList<>();

    public ErrorResponse() {
    }

    public ErrorResponse(String code, String message) {
        this.code = code;
        this.message = message;
    }

    public ErrorResponse(String code, String message, List<ErrorDetail> details) {
        this.code = code;
        this.message = message;
        if (details != null) {
            this.details = details;
        }
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
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
