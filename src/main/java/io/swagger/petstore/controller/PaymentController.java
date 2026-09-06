package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.data.PaymentData;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.Payment;
import io.swagger.petstore.model.PaymentRequest;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.service.AuthResult;
import io.swagger.petstore.service.AuthService;
import io.swagger.petstore.service.PaymentException;
import io.swagger.petstore.service.ValidationService;
import io.swagger.petstore.utils.Responses;
import io.swagger.petstore.utils.Util;

import javax.ws.rs.core.Response;
import java.util.List;
import java.util.UUID;

public class PaymentController {
    private static final PaymentData PAYMENT_DATA = new PaymentData();
    private final AuthService authService = AuthService.getInstance();

    public ResponseContext createPayment(final RequestContext request, final UUID orderId,
                                         final UUID idempotencyKey,
                                         final PaymentRequest body) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (orderId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Order id must be a valid UUID");
        }
        if (idempotencyKey == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "IDEMPOTENCY_KEY_REQUIRED",
                    "Idempotency-Key header is required");
        }
        final List<ErrorDetail> errors = ValidationService.validatePayment(body);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        try {
            final PaymentData.PaymentResult result = PAYMENT_DATA.createPayment(orderId, idempotencyKey, body,
                    auth.getUser(), auth.getUser().getRole() == Role.ADMIN);
            return new ResponseContext()
                    .status(result.isReplayed() ? Response.Status.OK : Response.Status.CREATED)
                    .contentType(Util.getMediaType(request))
                    .entity(result.getPayment());
        } catch (PaymentException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

    public ResponseContext listPayments(final RequestContext request, final UUID orderId) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (orderId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Order id must be a valid UUID");
        }
        try {
            return new ResponseContext()
                    .contentType(Util.getMediaType(request))
                    .entity(PAYMENT_DATA.findPayments(orderId, auth.getUser(),
                            auth.getUser().getRole() == Role.ADMIN));
        } catch (PaymentException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

    public ResponseContext getPayment(final RequestContext request, final UUID orderId,
                                      final UUID paymentId) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (orderId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Order id must be a valid UUID");
        }
        if (paymentId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Payment id must be a valid UUID");
        }
        try {
            final Payment payment = PAYMENT_DATA.getPayment(orderId, paymentId, auth.getUser(),
                    auth.getUser().getRole() == Role.ADMIN);
            return new ResponseContext().contentType(Util.getMediaType(request)).entity(payment);
        } catch (PaymentException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }
}
