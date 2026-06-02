package com.routechain.api.bigdata;

import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public final class NoopBigDataLitePersistentStore implements BigDataLitePersistentStore {
    @Override
    public void upsertJob(String jobId, String tenantId, String batchId, String queue, String kind, String status, int accepted, int rejected, int attempts) { }
    @Override
    public void appendEvent(String eventId, String jobId, String type, String timestamp, Map<String, Object> data) { }
    @Override
    public void markDeadLetter(String jobId, String reason) { }
    @Override
    public void upsertResult(String jobId, Map<String, Object> summary) { }
}
