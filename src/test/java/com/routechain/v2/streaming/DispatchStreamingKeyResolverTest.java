package com.routechain.v2.streaming;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Region;
import com.routechain.v2.DispatchV2Request;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DispatchStreamingKeyResolverTest {

    @Test
    void resolvesRegionTraceKeyForLoadBalancedPartitioning() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getStreaming().setKeyStrategy("region-trace");
        DispatchStreamingKeyResolver resolver = new DispatchStreamingKeyResolver(properties);
        DispatchV2Request request = new DispatchV2Request(
                "dispatch-v2-request/v1",
                "trace-1",
                List.of(),
                List.of(),
                List.of(new Region("region-a", "Region A")),
                null,
                Instant.parse("2026-04-16T12:00:00Z"));

        assertEquals("region-a:trace-1", resolver.key(request));
    }

    @Test
    void envelopeRegionKeyOverridesRequestKey() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        DispatchStreamingKeyResolver resolver = new DispatchStreamingKeyResolver(properties);
        DispatchStreamingEnvelope envelope = new DispatchStreamingEnvelope(
                "dispatch-streaming-envelope/v1",
                "event-1",
                "region-hot",
                Instant.parse("2026-04-16T12:00:00Z"),
                null,
                Map.of());

        assertEquals("region-hot", resolver.key(envelope));
    }
}
