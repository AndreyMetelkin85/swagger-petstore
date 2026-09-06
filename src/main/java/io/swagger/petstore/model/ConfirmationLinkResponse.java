package io.swagger.petstore.model;

public class ConfirmationLinkResponse {
    private String confirmationUrl;
    private String expiresAt;

    public ConfirmationLinkResponse() {
    }

    public ConfirmationLinkResponse(String confirmationUrl, String expiresAt) {
        this.confirmationUrl = confirmationUrl;
        this.expiresAt = expiresAt;
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
