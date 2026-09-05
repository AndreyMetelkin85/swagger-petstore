package io.swagger.petstore.model;

public class RegistrationResponse {
    private User user;
    private String confirmationUrl;
    private String expiresAt;

    public RegistrationResponse() {
    }

    public RegistrationResponse(User user, String confirmationUrl, String expiresAt) {
        this.user = user;
        this.confirmationUrl = confirmationUrl;
        this.expiresAt = expiresAt;
    }

    public User getUser() {
        return user;
    }

    public void setUser(User user) {
        this.user = user;
    }

    public String getConfirmationUrl() {
        return confirmationUrl;
    }

    public void setConfirmationUrl(String confirmationUrl) {
        this.confirmationUrl = confirmationUrl;
    }

    public String getExpiresAt() {
        return expiresAt;
    }

    public void setExpiresAt(String expiresAt) {
        this.expiresAt = expiresAt;
    }
}
