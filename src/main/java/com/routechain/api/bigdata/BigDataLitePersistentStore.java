package com.routechain.api.bigdata;

import java.util.Map;

public interface BigDataLitePersistentStore {
    void upsertJob(String jobId, String tenantId, String batchId, String queue, String kind, String status, int accepted, int rejected, int attempts);
    void appendEvent(String eventId, String jobId, String type, String timestamp, Map<String, Object> data);
    void markDeadLetter(String jobId, String reason);
    void upsertResult(String jobId, Map<String, Object> summary);
}
