package com.routechain.api.bigdata;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "routechain.live-kafka", name = "enabled", havingValue = "true")
public final class LiveKafkaBridge {
    private final KafkaTemplate<String, Object> kafkaTemplate;
    private final LiveKafkaProperties properties;
    private final BigDataLiteApiController controller;

    public LiveKafkaBridge(KafkaTemplate<String, Object> kafkaTemplate,
                           LiveKafkaProperties properties,
                           BigDataLiteApiController controller) {
        this.kafkaTemplate = kafkaTemplate;
        this.properties = properties;
        this.controller = controller;
    }

    public void publishOrder(LiveKafkaEnvelope envelope) {
        kafkaTemplate.send(properties.getOrderTopic(), key(envelope), envelope);
    }

    public void publishTelemetry(LiveKafkaEnvelope envelope) {
        kafkaTemplate.send(properties.getTelemetryTopic(), telemetryKey(envelope), envelope);
    }

    public void publishResult(Object result) {
        kafkaTemplate.send(properties.getResultTopic(), "live", result);
    }

    @KafkaListener(
            topics = "${routechain.live-kafka.order-topic:irx.live.orders.v1}",
            groupId = "${routechain.live-kafka.consumer-group-id:irx-live-dispatch}",
            containerFactory = "liveKafkaListenerContainerFactory")
    public void consumeOrder(LiveKafkaEnvelope envelope) {
        controller.acceptLiveKafkaOrder(envelope);
    }

    @KafkaListener(
            topics = "${routechain.live-kafka.telemetry-topic:irx.live.telemetry.v1}",
            groupId = "${routechain.live-kafka.consumer-group-id:irx-live-dispatch}",
            containerFactory = "liveKafkaListenerContainerFactory")
    public void consumeTelemetry(LiveKafkaEnvelope envelope) {
        controller.acceptLiveKafkaTelemetry(envelope);
    }

    private String key(LiveKafkaEnvelope envelope) {
        Object payload = envelope.payload();
        if (payload instanceof java.util.Map<?, ?> map) {
            String geo = geoCell(map);
            String timeBucket = timeBucket(map);
            String priority = priorityClass(map);
            return safe(envelope.tenantId()) + ":" + safe(envelope.regionId()) + ":" + geo + ":" + timeBucket + ":" + priority;
        }
        return safe(envelope.tenantId()) + ":" + safe(envelope.regionId()) + ":unknownGeo:normal:p0";
    }

    private String telemetryKey(LiveKafkaEnvelope envelope) {
        return safe(envelope.tenantId()) + ":" + safe(envelope.driverId());
    }

    private String safe(String value) {
        return value == null || value.isBlank() ? "unknown" : value;
    }

    private String geoCell(java.util.Map<?, ?> payload) {
        double lat = number(payload.get("pickupLat"), number(payload.get("lat"), 0.0));
        double lng = number(payload.get("pickupLng"), number(payload.get("lng"), 0.0));
        int latCell = (int) Math.floor(lat * 100.0);
        int lngCell = (int) Math.floor(lng * 100.0);
        return "g" + latCell + "_" + lngCell;
    }

    private String timeBucket(java.util.Map<?, ?> payload) {
        double eta = number(payload.get("promisedEtaMinutes"), 45.0);
        if (eta <= 15.0) return "urgent15";
        if (eta <= 30.0) return "hot30";
        if (eta <= 60.0) return "normal60";
        return "relaxed";
    }

    private String priorityClass(java.util.Map<?, ?> payload) {
        if (Boolean.parseBoolean(String.valueOf(payload.get("urgent")))) return "pU";
        int priority = (int) number(payload.get("priority"), 0.0);
        if (priority >= 8) return "pH";
        if (priority >= 4) return "pM";
        return "pL";
    }

    private double number(Object value, double fallback) {
        if (value instanceof Number number) return number.doubleValue();
        try { return value == null ? fallback : Double.parseDouble(String.valueOf(value)); } catch (NumberFormatException ignored) { return fallback; }
    }
}
