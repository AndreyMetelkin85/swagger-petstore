package io.swagger.petstore.service;

import io.swagger.petstore.model.AdminUserUpdateRequest;
import io.swagger.petstore.model.Address;
import io.swagger.petstore.model.Category;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.OrderCreateRequest;
import io.swagger.petstore.model.PasswordForgotRequest;
import io.swagger.petstore.model.PasswordResetRequest;
import io.swagger.petstore.model.PaymentRequest;
import io.swagger.petstore.model.PetCreateRequest;
import io.swagger.petstore.model.PetStatus;
import io.swagger.petstore.model.PetUpdateRequest;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.Tag;
import io.swagger.petstore.model.UserUpdateRequest;
import io.swagger.petstore.model.User;

import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;
import java.math.BigDecimal;
import java.time.YearMonth;

public final class ValidationService {
    private static final Pattern USERNAME = Pattern.compile("^[A-Za-z0-9_.-]{3,30}$");
    private static final Pattern TAG_NAME = Pattern.compile("^[A-Za-z0-9_.-]{1,30}$");
    private static final Pattern EMAIL = Pattern.compile("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");
    private static final Pattern PHONE = Pattern.compile("^\\+?[0-9 ()-]+$");
    private static final Pattern POSTAL_CODE = Pattern.compile("^[0-9]{6}$");
    private static final Pattern CARD_NUMBER = Pattern.compile("^[0-9]{13,19}$");
    private static final Pattern CVV = Pattern.compile("^[0-9]{3,4}$");
    private static final java.util.Set<String> TEST_CARDS = new java.util.HashSet<>(java.util.Arrays.asList(
            "4242424242424242", "4000000000000002", "4000000000009995"));
    private ValidationService() {
    }

    public static List<ErrorDetail> validateRegistration(RegisterRequest request) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (request == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        if (request.getUsername() == null || request.getUsername().trim().isEmpty()) {
            errors.add(new ErrorDetail("username", "Username is required"));
        } else if (!USERNAME.matcher(request.getUsername()).matches()) {
            errors.add(new ErrorDetail("username",
                    "Username must be 3-30 characters and contain only letters, digits, dot, underscore or hyphen"));
        }
        validatePassword(request.getPassword(), true, errors);
        validateEmail(request.getEmail(), true, errors);
        validateOptionalText("firstName", request.getFirstName(), 50, errors);
        validateOptionalText("lastName", request.getLastName(), 50, errors);
        validatePhone(request.getPhone(), errors);
        validateAddress(request.getAddress(), "address", errors);
        return errors;
    }

    public static List<ErrorDetail> validateLogin(String email, String password) {
        final List<ErrorDetail> errors = new ArrayList<>();
        validateEmail(email, true, errors);
        if (password == null || password.isEmpty()) {
            errors.add(new ErrorDetail("password", "Password is required"));
        }
        return errors;
    }

    public static List<ErrorDetail> validateUserUpdate(UserUpdateRequest request) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (request == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        request.getUnsupportedFields().keySet().forEach(field ->
                errors.add(new ErrorDetail(field, "Field is not allowed for profile update")));
        validateOptionalText("firstName", request.getFirstName(), 50, errors);
        validateOptionalText("lastName", request.getLastName(), 50, errors);
        validatePhone(request.getPhone(), errors);
        if (request.isAddressPresent()) {
            validateAddress(request.getAddress(), "address", errors);
        }
        if (request.getFirstName() == null && request.getLastName() == null
                && request.getPhone() == null && !request.isAddressPresent()) {
            errors.add(new ErrorDetail("body", "At least one profile field is required"));
        }
        return errors;
    }

    public static List<ErrorDetail> validatePasswordForgot(PasswordForgotRequest request) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (request == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        validateEmail(request.getEmail(), true, errors);
        return errors;
    }

    public static List<ErrorDetail> validatePasswordReset(PasswordResetRequest request) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (request == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        validatePassword(request.getNewPassword(), true, "newPassword", errors);
        return errors;
    }

    public static List<ErrorDetail> validateAdminUserUpdate(final AdminUserUpdateRequest request) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (request == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        request.getUnsupportedFields().keySet().forEach(field ->
                errors.add(new ErrorDetail(field, "Field is not allowed for administrator profile update")));
        if (request.getUsername() == null || request.getUsername().trim().isEmpty()) {
            errors.add(new ErrorDetail("username", "Username is required"));
        } else if (!USERNAME.matcher(request.getUsername()).matches()) {
            errors.add(new ErrorDetail("username",
                    "Username must be 3-30 characters and contain only letters, digits, dot, underscore or hyphen"));
        }
        validateEmail(request.getEmail(), true, errors);
        validateOptionalText("firstName", request.getFirstName(), 50, errors);
        validateOptionalText("lastName", request.getLastName(), 50, errors);
        validatePhone(request.getPhone(), errors);
        validateAddress(request.getAddress(), "address", errors);
        if (!request.isAddressPresent()) {
            errors.add(new ErrorDetail("address", "Address field is required and may be null"));
        }
        if (request.getRole() == null) {
            errors.add(new ErrorDetail("role", "Role is required"));
        }
        return errors;
    }

    public static List<ErrorDetail> validatePetCreate(final PetCreateRequest pet) {
        return validatePet(pet, false, null);
    }

    public static List<ErrorDetail> validatePetUpdate(final PetUpdateRequest pet) {
        final List<ErrorDetail> errors = validatePet(pet, false, null);
        if (pet != null && pet.getVersion() == null) {
            errors.add(new ErrorDetail("version", "Pet version is required"));
        } else if (pet != null && pet.getVersion() < 0) {
            errors.add(new ErrorDetail("version", "Pet version must not be negative"));
        }
        return errors;
    }

    private static List<ErrorDetail> validatePet(final PetCreateRequest pet, final boolean idRequired,
                                                 final Object id) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (pet == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        if (idRequired && id == null) {
            errors.add(new ErrorDetail("id", "Pet id is required and must be a valid UUID"));
        }
        if (pet.getName() == null || pet.getName().trim().isEmpty()) {
            errors.add(new ErrorDetail("name", "Pet name is required"));
        } else if (pet.getName().length() > 100) {
            errors.add(new ErrorDetail("name", "Pet name must not exceed 100 characters"));
        }
        validatePrice(pet.getPrice(), errors);
        if (PetStatus.RESERVED.getValue().equals(pet.getStatus())) {
            errors.add(new ErrorDetail("status", "Reserved status is managed by the order lifecycle"));
        } else if (pet.getStatus() != null
                && !PetStatus.AVAILABLE.getValue().equals(pet.getStatus())
                && !PetStatus.PENDING.getValue().equals(pet.getStatus())
                && !PetStatus.SOLD.getValue().equals(pet.getStatus())) {
            errors.add(new ErrorDetail("status", "Pet status must be available, pending or sold"));
        }
        validateCategory(pet.getCategory(), errors);
        validateTags(pet.getTags(), errors);
        if (pet.getPhotoUrls() != null && pet.getPhotoUrls().size() > 20) {
            errors.add(new ErrorDetail("photoUrls", "No more than 20 photo URLs are allowed"));
        }
        validatePhotoUrls(pet.getPhotoUrls(), errors);
        for (String field : pet.getUnsupportedFields().keySet()) {
            errors.add(new ErrorDetail(field, "Field is not allowed for this operation"));
        }
        return errors;
    }

    public static List<ErrorDetail> validateOrder(final OrderCreateRequest order) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (order == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        if (order.getPetId() == null) {
            errors.add(new ErrorDetail("petId", "Pet id is required and must be a valid UUID"));
        }
        if (order.getQuantity() == null || order.getQuantity() != 1) {
            errors.add(new ErrorDetail("quantity", "Quantity must be 1 for an individual pet"));
        }
        for (String field : order.getUnsupportedFields().keySet()) {
            errors.add(new ErrorDetail(field, "Field is managed by the server"));
        }
        return errors;
    }

    public static List<ErrorDetail> missingOrderProfileFields(final User user) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (user == null) {
            errors.add(new ErrorDetail("user", "User profile is required"));
            return errors;
        }
        requireText("firstName", user.getFirstName(), errors);
        requireText("lastName", user.getLastName(), errors);
        requireText("phone", user.getPhone(), errors);
        final Address address = user.getAddress();
        if (address == null) {
            errors.add(new ErrorDetail("address.city", "Field is required to place an order"));
            errors.add(new ErrorDetail("address.street", "Field is required to place an order"));
            errors.add(new ErrorDetail("address.house", "Field is required to place an order"));
            errors.add(new ErrorDetail("address.postalCode", "Field is required to place an order"));
        } else {
            requireText("address.city", address.getCity(), errors);
            requireText("address.street", address.getStreet(), errors);
            requireText("address.house", address.getHouse(), errors);
            requireText("address.postalCode", address.getPostalCode(), errors);
        }
        return errors;
    }

    public static List<ErrorDetail> validatePayment(final PaymentRequest payment) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (payment == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        final String cardNumber = payment.getCardNumber();
        if (cardNumber == null || !CARD_NUMBER.matcher(cardNumber).matches() || !passesLuhn(cardNumber)) {
            errors.add(new ErrorDetail("cardNumber", "Card number must be valid and pass the Luhn check"));
        } else if (!TEST_CARDS.contains(cardNumber)) {
            errors.add(new ErrorDetail("cardNumber", "Use one of the documented test card numbers"));
        }
        if (payment.getExpiryMonth() == null || payment.getExpiryMonth() < 1
                || payment.getExpiryMonth() > 12) {
            errors.add(new ErrorDetail("expiryMonth", "Expiry month must be between 1 and 12"));
        }
        if (payment.getExpiryYear() == null) {
            errors.add(new ErrorDetail("expiryYear", "Expiry year is required"));
        } else if (payment.getExpiryMonth() != null && payment.getExpiryMonth() >= 1
                && payment.getExpiryMonth() <= 12
                && YearMonth.of(payment.getExpiryYear(), payment.getExpiryMonth())
                .isBefore(YearMonth.now())) {
            errors.add(new ErrorDetail("expiryYear", "Card expiry date must not be in the past"));
        }
        if (payment.getCvv() == null || !CVV.matcher(payment.getCvv()).matches()) {
            errors.add(new ErrorDetail("cvv", "CVV must contain three or four digits"));
        }
        if (payment.getCardholderName() == null || payment.getCardholderName().trim().isEmpty()) {
            errors.add(new ErrorDetail("cardholderName", "Cardholder name is required"));
        } else if (payment.getCardholderName().length() > 100) {
            errors.add(new ErrorDetail("cardholderName", "Cardholder name must not exceed 100 characters"));
        }
        for (String field : payment.getUnsupportedFields().keySet()) {
            errors.add(new ErrorDetail(field, "Field is not allowed for payment"));
        }
        return errors;
    }

    private static void validateCategory(final Category category, final List<ErrorDetail> errors) {
        if (category == null) {
            return;
        }
        if (category.getName() == null || category.getName().trim().isEmpty()) {
            errors.add(new ErrorDetail("category.name", "Category name is required"));
        } else if (category.getName().length() > 50) {
            errors.add(new ErrorDetail("category.name", "Category name must not exceed 50 characters"));
        }
    }

    private static void validateTags(final List<Tag> tags, final List<ErrorDetail> errors) {
        if (tags == null) {
            return;
        }
        if (tags.size() > 20) {
            errors.add(new ErrorDetail("tags", "No more than 20 tags are allowed"));
        }
        for (int index = 0; index < tags.size(); index++) {
            final Tag tag = tags.get(index);
            final String field = "tags[" + index + "].name";
            if (tag == null || tag.getName() == null || tag.getName().trim().isEmpty()) {
                errors.add(new ErrorDetail(field, "Tag name is required"));
            } else if (tag.getName().length() > 30) {
                errors.add(new ErrorDetail(field, "Tag name must not exceed 30 characters"));
            } else if (!TAG_NAME.matcher(tag.getName()).matches()) {
                errors.add(new ErrorDetail(field,
                        "Tag name may contain only letters, digits, dot, underscore or hyphen"));
            }
        }
    }

    private static void validatePhotoUrls(final List<String> photoUrls,
                                          final List<ErrorDetail> errors) {
        if (photoUrls == null) {
            return;
        }
        for (int index = 0; index < photoUrls.size(); index++) {
            final String value = photoUrls.get(index);
            final String field = "photoUrls[" + index + "]";
            if (value == null || value.trim().isEmpty()) {
                errors.add(new ErrorDetail(field, "Photo URL is required"));
                continue;
            }
            if (value.length() > 2048) {
                errors.add(new ErrorDetail(field, "Photo URL must not exceed 2048 characters"));
                continue;
            }
            try {
                if (!new URI(value).isAbsolute()) {
                    errors.add(new ErrorDetail(field, "Photo URL must be an absolute URI"));
                }
            } catch (URISyntaxException exception) {
                errors.add(new ErrorDetail(field, "Photo URL must be a valid URI"));
            }
        }
    }

    private static void validateAddress(final Address address, final String prefix,
                                        final List<ErrorDetail> errors) {
        if (address == null) {
            return;
        }
        validateRequiredText(prefix + ".city", address.getCity(), 100, errors);
        validateRequiredText(prefix + ".street", address.getStreet(), 150, errors);
        validateRequiredText(prefix + ".house", address.getHouse(), 30, errors);
        validateOptionalText(prefix + ".apartment", address.getApartment(), 30, errors);
        if (address.getPostalCode() == null || !POSTAL_CODE.matcher(address.getPostalCode()).matches()) {
            errors.add(new ErrorDetail(prefix + ".postalCode", "Postal code must contain exactly six digits"));
        }
        address.getUnsupportedFields().keySet().forEach(field ->
                errors.add(new ErrorDetail(prefix + "." + field,
                        "Field is not allowed in a Russian delivery address")));
    }

    private static void validatePrice(final BigDecimal price, final List<ErrorDetail> errors) {
        if (price == null) {
            errors.add(new ErrorDetail("price", "Pet price is required"));
        } else if (price.compareTo(new BigDecimal("0.01")) < 0) {
            errors.add(new ErrorDetail("price", "Pet price must be at least 0.01"));
        } else if (price.scale() > 2) {
            errors.add(new ErrorDetail("price", "Pet price must have no more than two decimal places"));
        } else if (price.compareTo(new BigDecimal("9999999999.99")) > 0) {
            errors.add(new ErrorDetail("price", "Pet price is too large"));
        }
    }

    private static void validatePhone(final String phone, final List<ErrorDetail> errors) {
        if (phone != null && (phone.length() < 7 || phone.length() > 30
                || !PHONE.matcher(phone).matches())) {
            errors.add(new ErrorDetail("phone", "Phone must contain 7-30 digits and phone punctuation"));
        }
    }

    private static void validateRequiredText(final String field, final String value,
                                             final int maxLength, final List<ErrorDetail> errors) {
        if (value == null || value.trim().isEmpty()) {
            errors.add(new ErrorDetail(field, "Field is required"));
        } else if (value.length() > maxLength) {
            errors.add(new ErrorDetail(field, field + " must not exceed " + maxLength + " characters"));
        }
    }

    private static void requireText(final String field, final String value,
                                    final List<ErrorDetail> errors) {
        if (value == null || value.trim().isEmpty()) {
            errors.add(new ErrorDetail(field, "Field is required to place an order"));
        }
    }

    private static boolean passesLuhn(final String value) {
        if (value == null || !CARD_NUMBER.matcher(value).matches()) {
            return false;
        }
        int sum = 0;
        boolean doubled = false;
        for (int index = value.length() - 1; index >= 0; index--) {
            int digit = value.charAt(index) - '0';
            if (doubled) {
                digit *= 2;
                if (digit > 9) {
                    digit -= 9;
                }
            }
            sum += digit;
            doubled = !doubled;
        }
        return sum % 10 == 0;
    }

    private static void validatePassword(String password, boolean required, List<ErrorDetail> errors) {
        validatePassword(password, required, "password", errors);
    }

    private static void validatePassword(String password, boolean required, String field,
                                         List<ErrorDetail> errors) {
        if (password == null || password.isEmpty()) {
            if (required) {
                errors.add(new ErrorDetail(field, "Password is required"));
            }
        } else if (password.length() < 6 || password.length() > 100) {
            errors.add(new ErrorDetail(field, "Password must be between 6 and 100 characters"));
        } else if (password.getBytes(StandardCharsets.UTF_8).length > 72) {
            errors.add(new ErrorDetail(field, "Password must not exceed 72 UTF-8 bytes"));
        }
    }

    private static void validateEmail(String email, boolean required, List<ErrorDetail> errors) {
        if (email == null || email.trim().isEmpty()) {
            if (required) {
                errors.add(new ErrorDetail("email", "Email is required"));
            }
        } else if (email.length() > 254 || !EMAIL.matcher(email).matches()) {
            errors.add(new ErrorDetail("email", "Email must be a valid email address"));
        }
    }

    private static void validateOptionalText(final String field, final String value, final int maxLength,
                                             final List<ErrorDetail> errors) {
        if (value == null) {
            return;
        }
        if (value.trim().isEmpty()) {
            errors.add(new ErrorDetail(field, field + " must not be blank"));
        } else if (value.length() > maxLength) {
            errors.add(new ErrorDetail(field, field + " must not exceed " + maxLength + " characters"));
        }
    }
}
