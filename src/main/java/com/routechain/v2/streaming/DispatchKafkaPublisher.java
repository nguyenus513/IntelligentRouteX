package com.routechain.v2.streaming;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchV2Result;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Component
@ConditionalOnProperty(prefix = "routechain.dispatch-v2.streaming", name = "enabled", havingValue = "true")
public final class DispatchKafkaPublisher {
    private final RouteChainDispatchV2Properties properties;
    private final KafkaTemplate<String, Object> kafkaTemplate;
    private final DispatchBigDataSink bigDataSink;
    private final DispatchStreamingMetrics metrics;

    public DispatchKafkaPublisher(RouteChainDispatchV2Properties properties,
                                  KafkaTemplate<String, Object> kafkaTemplate,
                                  DispatchBigDataSink bigDataSink,
                                  DispatchStreamingMetrics metrics) {
        this.properties = properties;
        this.kafkaTemplate = kafkaTemplate;
        this.bigDataSink = bigDataSink;
        this.metrics = metrics;
    }

    public void publishResult(String key, DispatchV2Result result) {
        DispatchStreamingResultEnvelope envelope = new DispatchStreamingResultEnvelope(
                "dispatch-streaming-result-envelope/v1",
                result.traceId() + ":result",
                result.traceId(),
                key,
                Instant.now(),
                result,
                java.util.Map.of("assignmentCount", Integer.toString(result.assignments().size())));
        kafkaTemplate.send(properties.getStreaming().getOutputTopic(), key, envelope);
        metrics.markProduced();
        bigDataSink.writeDispatchResult(envelope);
        if (properties.getStreaming().isPublishTrainingTrace()) {
            bigDataSink.writeTrainingTraces(result.traceId(), result.globalSelectorSummary() == null
                    ? java.util.List.of()
                    : java.util.List.of());
        }
    }

    public void publishDeadLetter(String key, DispatchStreamingEnvelope envelope, Exception exception) {
        kafkaTemplate.send(properties.getStreaming().getDeadLetterTopic(), key, java.util.Map.of(
                "schemaVersion", "dispatch-streaming-dlq/v1",
                "eventId", envelope == null ? "unknown" : envelope.eventId(),
                "traceId", envelope == null || envelope.request() == null ? "unknown" : envelope.request().traceId(),
                "error", exception == null ? "unknown" : exception.getClass().getSimpleName(),
                "message", exception == null || exception.getMessage() == null ? "" : exception.getMessage()));
        metrics.markDeadLetter();
    }
}
