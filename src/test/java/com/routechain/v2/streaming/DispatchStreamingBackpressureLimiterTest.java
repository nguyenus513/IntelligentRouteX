package com.routechain.v2.streaming;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchStreamingBackpressureLimiterTest {

    @Test
    void rejectsWhenMaxInFlightExceeded() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getStreaming().setMaxInFlight(1);
        DispatchStreamingMetrics metrics = new DispatchStreamingMetrics();
        DispatchStreamingBackpressureLimiter limiter = new DispatchStreamingBackpressureLimiter(properties, metrics);

        DispatchStreamingBackpressureLimiter.Permit first = limiter.tryAcquire();
        DispatchStreamingBackpressureLimiter.Permit second = limiter.tryAcquire();

        assertTrue(first.acquired());
        assertFalse(second.acquired());
        assertTrue(metrics.snapshot().rejectedBackpressureCount() > 0);
        limiter.release(first);
    }
}
