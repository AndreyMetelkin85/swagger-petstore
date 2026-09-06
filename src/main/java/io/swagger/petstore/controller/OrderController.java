package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.data.OrderData;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.Order;
import io.swagger.petstore.model.OrderCreateRequest;
import io.swagger.petstore.model.OrderStatus;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.service.AuthResult;
import io.swagger.petstore.service.AuthService;
import io.swagger.petstore.service.OrderException;
import io.swagger.petstore.service.ValidationService;
import io.swagger.petstore.utils.Responses;
import io.swagger.petstore.utils.Util;

import javax.ws.rs.core.Response;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public class OrderController {
    private static final OrderData ORDER_DATA = new OrderData();
    private final AuthService authService = AuthService.getInstance();

    public ResponseContext getInventory(final RequestContext request) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(ORDER_DATA.getCountByStatus());
    }

    public ResponseContext listOrders(final RequestContext request) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(auth.getUser().getRole() == Role.ADMIN
                        ? ORDER_DATA.findAll()
                        : ORDER_DATA.findOrdersForUser(auth.getUser().getId()));
    }

    public ResponseContext getOrderById(final RequestContext request, final UUID orderId) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (orderId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Order id must be a valid UUID");
        }
        final Order order = ORDER_DATA.getOrderById(orderId);
        if (order == null) {
            return Responses.error(Response.Status.NOT_FOUND, "ORDER_NOT_FOUND", "Order was not found");
        }
        if (auth.getUser().getRole() != Role.ADMIN
                && !Objects.equals(auth.getUser().getId(), ORDER_DATA.getOrderOwner(orderId))) {
            return Responses.error(Response.Status.FORBIDDEN, "ORDER_ACCESS_DENIED",
                    "Users may access only their own orders");
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(order);
    }

    public ResponseContext placeOrder(final RequestContext request, final OrderCreateRequest order) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final List<ErrorDetail> errors = ValidationService.validateOrder(order);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        final List<ErrorDetail> missingProfile =
                ValidationService.missingOrderProfileFields(auth.getUser());
        if (!missingProfile.isEmpty()) {
            return Responses.error(Response.Status.CONFLICT, "PROFILE_INCOMPLETE",
                    "Complete the delivery profile before placing an order", missingProfile);
        }
        try {
            final Order created = ORDER_DATA.placeOrder(order, auth.getUser());
            return new ResponseContext()
                    .status(Response.Status.CREATED)
                    .contentType(Util.getMediaType(request))
                    .entity(created);
        } catch (OrderException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

    public ResponseContext approveOrder(final RequestContext request, final UUID orderId) {
        return transition(request, orderId, OrderStatus.APPROVED, true);
    }

    public ResponseContext shipOrder(final RequestContext request, final UUID orderId) {
        return transition(request, orderId, OrderStatus.SHIPPED, true);
    }

    public ResponseContext deliverOrder(final RequestContext request, final UUID orderId) {
        return transition(request, orderId, OrderStatus.DELIVERED, true);
    }

    public ResponseContext cancelOrder(final RequestContext request, final UUID orderId) {
        return transition(request, orderId, OrderStatus.CANCELLED, false);
    }

    private ResponseContext transition(final RequestContext request, final UUID orderId,
                                       final OrderStatus target, final boolean adminOnly) {
        final AuthResult auth = adminOnly
                ? authService.authorize(request, Role.ADMIN)
                : authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (orderId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Order id must be a valid UUID");
        }
        try {
            final Order updated = ORDER_DATA.transition(orderId, target,
                    auth.getUser().getId(), auth.getUser().getRole() == Role.ADMIN);
            return new ResponseContext()
                    .contentType(Util.getMediaType(request))
                    .entity(updated);
        } catch (OrderException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

}
