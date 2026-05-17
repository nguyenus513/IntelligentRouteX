package com.routechain.runtime.store;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryDispatchJobStore implements DispatchJobStore {
    private final Map<String, RuntimeJobRecord> jobs = new ConcurrentHashMap<>();
    public RuntimeJobRecord save(RuntimeJobRecord job) { jobs.put(key(job.tenantId(), job.jobId()), job); return job; }
    public Optional<RuntimeJobRecord> find(String tenantId, String jobId) { return Optional.ofNullable(jobs.get(key(tenantId, jobId))); }
    public RuntimeJobRecord updateStatus(String tenantId, String jobId, String status, String resultId, String error) {
        RuntimeJobRecord current = jobs.get(key(tenantId, jobId));
        RuntimeJobRecord next = new RuntimeJobRecord(jobId, tenantId, current == null ? "FAST" : current.lane(), status, current == null ? Instant.now() : current.createdAt(), Instant.now(), resultId, error);
        jobs.put(key(tenantId, jobId), next);
        return next;
    }
    private String key(String tenantId, String jobId) { return tenantId + ":" + jobId; }
}
