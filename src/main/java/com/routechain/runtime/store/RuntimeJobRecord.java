package com.routechain.runtime.store;

import java.time.Instant;

public record RuntimeJobRecord(String jobId, String tenantId, String lane, String status, Instant createdAt, Instant updatedAt, String resultId, String error) { }
