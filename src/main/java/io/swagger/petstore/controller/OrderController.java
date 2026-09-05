package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.data.OrderData;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.Order;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.service.AuthResult;
import io.swagger.petstore.service.AuthService;
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
                .entity(ORDER_DATA.findOrdersForUser(auth.getUser().getUsername()));
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
                && !Objects.equals(auth.getUser().getUsername(), ORDER_DATA.getOrderOwner(orderId))) {
            return Responses.error(Response.Status.FORBIDDEN, "FORBIDDEN",
                    "Users may access only their own orders");
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(order);
    }

    public ResponseContext placeOrder(final RequestContext request, final Order order) {
        final AuthResult auth = authService.authorize(request, Role.USER, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final List<ErrorDetail> errors = ValidationService.validateOrder(order);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        ORDER_DATA.addOrder(order, auth.getUser().getUsername());
        return new ResponseContext()
                .status(Response.Status.CREATED)
                .contentType(Util.getMediaType(request))
                .entity(order);
    }

    public ResponseContext deleteOrder(final RequestContext request, final UUID orderId) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (orderId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Order id must be a valid UUID");
        }
        if (!ORDER_DATA.deleteOrderById(orderId)) {
            return Responses.error(Response.Status.NOT_FOUND, "ORDER_NOT_FOUND", "Order was not found");
        }
        return new ResponseContext().status(Response.Status.NO_CONTENT);
    }

}
