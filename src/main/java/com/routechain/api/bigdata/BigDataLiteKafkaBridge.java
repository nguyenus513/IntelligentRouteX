package com.routechain.api.bigdata;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "routechain.bigdata-lite.kafka", name = "enabled", havingValue = "true")
public final class BigDataLiteKafkaBridge {
    private final KafkaTemplate<String, Object> kafkaTemplate;
    private final BigDataLiteApiController controller;
    private final BigDataLiteKafkaProperties properties;

    public BigDataLiteKafkaBridge(KafkaTemplate<String, Object> kafkaTemplate,
                                  BigDataLiteApiController controller,
                                  BigDataLiteKafkaProperties properties) {
        this.kafkaTemplate = kafkaTemplate;
        this.controller = controller;
        this.properties = properties;
    }

    public void publish(BigDataLiteKafkaEnvelope envelope) {
        kafkaTemplate.send(properties.getInputTopic(), key(envelope), envelope);
    }

    public void publishResult(String jobId, String tenantId, String batchId, Object result) {
        String key = (tenantId == null || tenantId.isBlank() ? "unknown" : tenantId) + ":" + (batchId == null || batchId.isBlank() ? jobId : batchId);
        kafkaTemplate.send(properties.getResultTopic(), key, result);
    }

    @KafkaListener(
            topics = "${routechain.bigdata-lite.kafka.input-topic:irx.bigdata.chunks.v1}",
            groupId = "${routechain.bigdata-lite.kafka.consumer-group-id:irx-bigdata-lite}",
            containerFactory = "bigDataLiteKafkaListenerContainerFactory")
    public void consume(BigDataLiteKafkaEnvelope envelope) {
        controller.executeKafkaEnvelope(envelope);
    }

    private String key(BigDataLiteKafkaEnvelope envelope) {
        if (envelope == null) return "unknown";
        String tenant = envelope.tenantId() == null || envelope.tenantId().isBlank() ? "unknown" : envelope.tenantId();
        String batch = envelope.batchId() == null || envelope.batchId().isBlank() ? envelope.jobId() : envelope.batchId();
        return tenant + ":" + batch;
    }
}
