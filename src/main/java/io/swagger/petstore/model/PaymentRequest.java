package io.swagger.petstore.model;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonIgnore;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class PaymentRequest {
    private String cardNumber;
    private Integer expiryMonth;
    private Integer expiryYear;
    private String cvv;
    private String cardholderName;
    private final Map<String, Object> unsupportedFields = new LinkedHashMap<>();

    public String getCardNumber() {
        return cardNumber;
    }

    public void setCardNumber(final String cardNumber) {
        this.cardNumber = cardNumber;
    }

    public Integer getExpiryMonth() {
        return expiryMonth;
    }

    public void setExpiryMonth(final Integer expiryMonth) {
        this.expiryMonth = expiryMonth;
    }

    public Integer getExpiryYear() {
        return expiryYear;
    }

    public void setExpiryYear(final Integer expiryYear) {
        this.expiryYear = expiryYear;
    }

    public String getCvv() {
        return cvv;
    }

    public void setCvv(final String cvv) {
        this.cvv = cvv;
    }

    public String getCardholderName() {
        return cardholderName;
    }

    public void setCardholderName(final String cardholderName) {
        this.cardholderName = cardholderName;
    }

    @JsonAnySetter
    public void captureUnsupportedField(final String name, final Object value) {
        unsupportedFields.put(name, value);
    }

    @JsonIgnore
    public Map<String, Object> getUnsupportedFields() {
        return Collections.unmodifiableMap(unsupportedFields);
    }
}
