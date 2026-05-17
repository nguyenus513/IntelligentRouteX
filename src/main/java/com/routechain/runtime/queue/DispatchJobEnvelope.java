package com.routechain.runtime.queue;

import java.time.Instant;

public record DispatchJobEnvelope(String jobId, String tenantId, QueueLane lane, int priority, Instant createdAt) { }
