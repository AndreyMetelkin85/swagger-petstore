package io.swagger.petstore.service;

import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.Order;
import io.swagger.petstore.model.PasswordForgotRequest;
import io.swagger.petstore.model.PasswordResetRequest;
import io.swagger.petstore.model.Pet;
import io.swagger.petstore.model.RegisterRequest;
import io.swagger.petstore.model.UserUpdateRequest;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.regex.Pattern;

public final class ValidationService {
    private static final Pattern USERNAME = Pattern.compile("^[A-Za-z0-9_.-]{3,30}$");
    private static final Pattern EMAIL = Pattern.compile("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");
    private static final List<String> PET_STATUSES = Arrays.asList("available", "pending", "sold");
    private static final List<String> ORDER_STATUSES = Arrays.asList("placed", "approved", "delivered");

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

    public static List<ErrorDetail> validateLogin(String username, String password) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (username == null || username.trim().isEmpty()) {
            errors.add(new ErrorDetail("username", "Username is required"));
        }
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
        validatePassword(request.getPassword(), false, errors);
        validateEmail(request.getEmail(), false, errors);
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

    public static List<ErrorDetail> validatePet(Pet pet, boolean idRequired) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (pet == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        if (idRequired && pet.getId() == null) {
            errors.add(new ErrorDetail("id", "Pet id is required and must be a valid UUID"));
        }
        if (pet.getName() == null || pet.getName().trim().isEmpty()) {
            errors.add(new ErrorDetail("name", "Pet name is required"));
        } else if (pet.getName().length() > 100) {
            errors.add(new ErrorDetail("name", "Pet name must not exceed 100 characters"));
        }
        if (pet.getStatus() != null && !PET_STATUSES.contains(pet.getStatus())) {
            errors.add(new ErrorDetail("status", "Pet status must be available, pending or sold"));
        }
        return errors;
    }

    public static List<ErrorDetail> validateOrder(Order order) {
        final List<ErrorDetail> errors = new ArrayList<>();
        if (order == null) {
            errors.add(new ErrorDetail("body", "Request body is required"));
            return errors;
        }
        if (order.getPetId() == null) {
            errors.add(new ErrorDetail("petId", "Pet id is required and must be a valid UUID"));
        }
        if (order.getQuantity() == null || order.getQuantity() < 1 || order.getQuantity() > 100) {
            errors.add(new ErrorDetail("quantity", "Quantity must be between 1 and 100"));
        }
        if (order.getStatus() != null && !ORDER_STATUSES.contains(order.getStatus())) {
            errors.add(new ErrorDetail("status", "Order status must be placed, approved or delivered"));
        }
        return errors;
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
}
