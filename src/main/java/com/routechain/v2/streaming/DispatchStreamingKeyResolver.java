package com.routechain.v2.streaming;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchV2Request;

public final class DispatchStreamingKeyResolver {
    private final RouteChainDispatchV2Properties properties;

    public DispatchStreamingKeyResolver(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public String key(DispatchStreamingEnvelope envelope) {
        if (envelope == null) {
            return "unknown";
        }
        if (envelope.regionKey() != null && !envelope.regionKey().isBlank()) {
            return envelope.regionKey();
        }
        return key(envelope.request());
    }

    public String key(DispatchV2Request request) {
        if (request == null) {
            return "unknown";
        }
        String strategy = properties.getStreaming().getKeyStrategy();
        if ("trace".equalsIgnoreCase(strategy)) {
            return safe(request.traceId());
        }
        String region = request.regions() == null || request.regions().isEmpty()
                ? "global"
                : safe(request.regions().getFirst().regionId());
        if ("region".equalsIgnoreCase(strategy)) {
            return region;
        }
        return region + ":" + safe(request.traceId());
    }

    private String safe(String value) {
        return value == null || value.isBlank() ? "unknown" : value;
    }
}
