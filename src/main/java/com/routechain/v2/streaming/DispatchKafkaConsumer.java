package com.routechain.v2.streaming;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchV2Core;
import com.routechain.v2.DispatchV2Result;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "routechain.dispatch-v2.streaming", name = "enabled", havingValue = "true")
public final class DispatchKafkaConsumer {
    private final RouteChainDispatchV2Properties properties;
    private final DispatchV2Core dispatchV2Core;
    private final DispatchStreamingKeyResolver keyResolver;
    private final DispatchKafkaPublisher publisher;
    private final DispatchStreamingBackpressureLimiter backpressureLimiter;
    private final DispatchStreamingMetrics metrics;

    public DispatchKafkaConsumer(RouteChainDispatchV2Properties properties,
                                 DispatchV2Core dispatchV2Core,
                                 DispatchStreamingKeyResolver keyResolver,
                                 DispatchKafkaPublisher publisher,
                                 DispatchStreamingBackpressureLimiter backpressureLimiter,
                                 DispatchStreamingMetrics metrics) {
        this.properties = properties;
        this.dispatchV2Core = dispatchV2Core;
        this.keyResolver = keyResolver;
        this.publisher = publisher;
        this.backpressureLimiter = backpressureLimiter;
        this.metrics = metrics;
    }

    @KafkaListener(
            topics = "${routechain.dispatch-v2.streaming.input-topic}",
            groupId = "${routechain.dispatch-v2.streaming.consumer-group-id}",
            containerFactory = "dispatchKafkaListenerContainerFactory")
    public void consume(DispatchStreamingEnvelope envelope) {
        long startedAt = System.nanoTime();
        String key = keyResolver.key(envelope);
        DispatchStreamingBackpressureLimiter.Permit permit = backpressureLimiter.tryAcquire();
        if (!permit.acquired()) {
            publisher.publishDeadLetter(key, envelope, new IllegalStateException("streaming backpressure max-in-flight exceeded"));
            return;
        }
        try {
            metrics.markConsumed();
            if (envelope == null || envelope.request() == null) {
                throw new IllegalArgumentException("missing dispatch request envelope");
            }
            DispatchV2Result result = dispatchV2Core.dispatch(envelope.request());
            publisher.publishResult(key, result);
        } catch (Exception exception) {
            publisher.publishDeadLetter(key, envelope, exception);
            if (properties.isSidecarRequired()) {
                throw exception;
            }
        } finally {
            metrics.addLatency((System.nanoTime() - startedAt) / 1_000_000L);
            backpressureLimiter.release(permit);
        }
    }
}
