package com.routechain.runtime.store;

import java.util.Optional;

public interface DispatchJobStore {
    RuntimeJobRecord save(RuntimeJobRecord job);
    Optional<RuntimeJobRecord> find(String tenantId, String jobId);
    RuntimeJobRecord updateStatus(String tenantId, String jobId, String status, String resultId, String error);
}
