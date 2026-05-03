package com.routechain.v2.streaming;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.springframework.stereotype.Component;

@Component
public final class DispatchStreamingBackpressureLimiter {
    private final RouteChainDispatchV2Properties properties;
    private final DispatchStreamingMetrics metrics;

    public DispatchStreamingBackpressureLimiter(RouteChainDispatchV2Properties properties,
                                                DispatchStreamingMetrics metrics) {
        this.properties = properties;
        this.metrics = metrics;
    }

    public Permit tryAcquire() {
        int inFlight = metrics.incrementInFlight();
        int maxInFlight = Math.max(1, properties.getStreaming().getMaxInFlight());
        if (inFlight > maxInFlight) {
            metrics.decrementInFlight();
            metrics.markRejectedBackpressure();
            return new Permit(false, inFlight, maxInFlight);
        }
        return new Permit(true, inFlight, maxInFlight);
    }

    public void release(Permit permit) {
        if (permit != null && permit.acquired()) {
            metrics.decrementInFlight();
        }
    }

    public record Permit(boolean acquired, int inFlight, int maxInFlight) {
    }
}
