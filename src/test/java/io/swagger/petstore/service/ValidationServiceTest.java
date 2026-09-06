package io.swagger.petstore.service;

import io.swagger.petstore.model.Address;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.PaymentRequest;
import io.swagger.petstore.model.PetCreateRequest;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.User;
import org.junit.Test;

import java.math.BigDecimal;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class ValidationServiceTest {
    @Test
    public void validatesCompleteAddressAndSixDigitPostalCode() {
        final RegisterRequest request = registration();
        request.setAddress(address("123456"));
        assertTrue(ValidationService.validateRegistration(request).isEmpty());

        request.setAddress(address("12345"));
        assertEquals("address.postalCode",
                ValidationService.validateRegistration(request).get(0).getField());

        request.setAddress(address("012345"));
        assertTrue(ValidationService.validateRegistration(request).isEmpty());

        request.getAddress().captureUnsupportedField("country", "RU");
        assertTrue(fields(ValidationService.validateRegistration(request)).contains("address.country"));

        request.setAddress(address("012345"));
        request.getAddress().setStreet(null);
        assertTrue(fields(ValidationService.validateRegistration(request)).contains("address.street"));
    }

    @Test
    public void validatesPetPriceScaleAndMinimum() {
        final PetCreateRequest request = new PetCreateRequest();
        request.setName("Luna");
        request.setPrice(new BigDecimal("100.00"));
        assertTrue(ValidationService.validatePetCreate(request).isEmpty());

        request.setPrice(new BigDecimal("0.001"));
        assertTrue(fields(ValidationService.validatePetCreate(request)).contains("price"));
    }

    @Test
    public void validatesOnlyDocumentedTestCards() {
        final PaymentRequest request = payment("4242424242424242");
        assertTrue(ValidationService.validatePayment(request).isEmpty());

        request.setCardNumber("4242424242424241");
        assertEquals("cardNumber", ValidationService.validatePayment(request).get(0).getField());
    }

    @Test
    public void reportsAllMissingCheckoutProfileFields() {
        final User user = new User();
        final List<String> fields = fields(ValidationService.missingOrderProfileFields(user));
        assertTrue(fields.contains("firstName"));
        assertTrue(fields.contains("lastName"));
        assertTrue(fields.contains("phone"));
        assertTrue(fields.contains("address.city"));
        assertTrue(fields.contains("address.postalCode"));
    }

    private static RegisterRequest registration() {
        final RegisterRequest request = new RegisterRequest();
        request.setUsername("qa_user");
        request.setPassword("SecurePass123");
        request.setEmail("qa@example.test");
        return request;
    }

    private static Address address(final String postalCode) {
        final Address address = new Address();
        address.setCity("Москва");
        address.setStreet("Федорова");
        address.setHouse("30");
        address.setApartment("12");
        address.setPostalCode(postalCode);
        return address;
    }

    private static PaymentRequest payment(final String cardNumber) {
        final PaymentRequest request = new PaymentRequest();
        request.setCardNumber(cardNumber);
        request.setExpiryMonth(12);
        request.setExpiryYear(2099);
        request.setCvv("123");
        request.setCardholderName("IVAN IVANOV");
        return request;
    }

    private static List<String> fields(final List<ErrorDetail> errors) {
        final java.util.ArrayList<String> fields = new java.util.ArrayList<>();
        for (ErrorDetail error : errors) {
            fields.add(error.getField());
        }
        return fields;
    }
}
