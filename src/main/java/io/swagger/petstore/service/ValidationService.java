package io.swagger.petstore.service;

import io.swagger.petstore.model.AdminUserUpdateRequest;
import io.swagger.petstore.model.Category;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.OrderCreateRequest;
import io.swagger.petstore.model.PasswordForgotRequest;
import io.swagger.petstore.model.PasswordResetRequest;
import io.swagger.petstore.model.PetCreateRequest;
import io.swagger.petstore.model.PetStatus;
import io.swagger.petstore.model.PetUpdateRequest;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.Tag;
import io.swagger.petstore.model.UserUpdateRequest;

import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

public final class ValidationService {
    private static final Pattern USERNAME = Pattern.compile("^[A-Za-z0-9_.-]{3,30}$");
    private static final Pattern TAG_NAME = Pattern.compile("^[A-Za-z0-9_.-]{1,30}$");
    private static final Pattern EMAIL = Pattern.compile("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");
    private static final Pattern PHONE = Pattern.compile("^\\+?[0-9 ()-]+$");
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
        if (request.getPhone() != null && (request.getPhone().length() < 7
                || request.getPhone().length() > 30 || !PHONE.matcher(request.getPhone()).matches())) {
            errors.add(new ErrorDetail("phone", "Phone must contain 7-30 digits and phone punctuation"));
        }
        if (request.getFirstName() == null && request.getLastName() == null
                && request.getPhone() == null) {
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
        if (request.getPhone() != null && (request.getPhone().length() < 7
                || request.getPhone().length() > 30 || !PHONE.matcher(request.getPhone()).matches())) {
            errors.add(new ErrorDetail("phone", "Phone must contain 7-30 digits and phone punctuation"));
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
