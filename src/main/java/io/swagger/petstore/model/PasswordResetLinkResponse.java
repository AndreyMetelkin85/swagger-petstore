package io.swagger.petstore.model;

public class PasswordResetLinkResponse {
    private String resetUrl;
    private String expiresAt;

    public PasswordResetLinkResponse() {
    }

    public PasswordResetLinkResponse(String resetUrl, String expiresAt) {
        this.resetUrl = resetUrl;
        this.expiresAt = expiresAt;
    }

    public String getResetUrl() {
        return resetUrl;
    }

    public void setResetUrl(String resetUrl) {
        this.resetUrl = resetUrl;
    }

    public String getExpiresAt() {
        return expiresAt;
    }

    public void setExpiresAt(String expiresAt) {
        this.expiresAt = expiresAt;
    }
}
