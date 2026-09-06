package io.swagger.petstore.model;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class OrderStatusTest {
    @Test
    public void allowsOnlyConfiguredOrderLifecycleTransitions() {
        assertTrue(OrderStatus.PLACED.canTransitionTo(OrderStatus.APPROVED));
        assertTrue(OrderStatus.PLACED.canTransitionTo(OrderStatus.CANCELLED));
        assertTrue(OrderStatus.APPROVED.canTransitionTo(OrderStatus.SHIPPED));
        assertTrue(OrderStatus.APPROVED.canTransitionTo(OrderStatus.CANCELLED));
        assertTrue(OrderStatus.SHIPPED.canTransitionTo(OrderStatus.DELIVERED));

        assertFalse(OrderStatus.PLACED.canTransitionTo(OrderStatus.DELIVERED));
        assertFalse(OrderStatus.SHIPPED.canTransitionTo(OrderStatus.CANCELLED));
        assertFalse(OrderStatus.DELIVERED.canTransitionTo(OrderStatus.CANCELLED));
        assertFalse(OrderStatus.CANCELLED.canTransitionTo(OrderStatus.APPROVED));
    }
}
