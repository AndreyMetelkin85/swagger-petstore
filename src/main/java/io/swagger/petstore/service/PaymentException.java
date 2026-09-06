package io.swagger.petstore.service;

/** Expected payment-domain failure mapped by the controller to the public error contract. */
public class PaymentException extends RuntimeException {
    private static final long serialVersionUID = 1L;
    private final int status;
    private final String code;

    public PaymentException(final int status, final String code, final String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public int getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }
}
