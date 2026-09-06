package io.swagger.petstore.model;

import com.fasterxml.jackson.annotation.JsonProperty;

public class PasswordResetRequest {
    private String newPassword;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    public String getNewPassword() {
        return newPassword;
    }

    public void setNewPassword(String newPassword) {
        this.newPassword = newPassword;
    }
}
