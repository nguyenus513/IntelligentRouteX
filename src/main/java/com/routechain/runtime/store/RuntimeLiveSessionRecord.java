package com.routechain.runtime.store;

import java.time.Instant;
import java.util.Map;

public record RuntimeLiveSessionRecord(String sessionId, String tenantId, String status, Instant createdAt, Map<String, Object> state) { }
