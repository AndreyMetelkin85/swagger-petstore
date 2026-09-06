package io.swagger.petstore.service;

import io.swagger.petstore.data.OrderData;

import javax.servlet.ServletContextEvent;
import javax.servlet.ServletContextListener;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

/** Runs the local reservation expiry job while the API application is active. */
public class OrderExpirationListener implements ServletContextListener {
    private ScheduledExecutorService executor;

    @Override
    public void contextInitialized(final ServletContextEvent event) {
        executor = Executors.newSingleThreadScheduledExecutor(new ThreadFactory() {
            @Override
            public Thread newThread(final Runnable runnable) {
                final Thread thread = new Thread(runnable, "petstore-order-expiration");
                thread.setDaemon(true);
                return thread;
            }
        });
        executor.scheduleWithFixedDelay(new Runnable() {
            @Override
            public void run() {
                try {
                    new OrderData().expireOverdueOrders();
                } catch (RuntimeException exception) {
                    event.getServletContext().log("Failed to expire unpaid orders", exception);
                }
            }
        }, 30L, 30L, TimeUnit.SECONDS);
    }

    @Override
    public void contextDestroyed(final ServletContextEvent event) {
        if (executor != null) {
            executor.shutdownNow();
        }
    }
}
