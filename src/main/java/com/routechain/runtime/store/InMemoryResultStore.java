package com.routechain.runtime.store;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryResultStore implements ResultStore {
    private final Map<String, Object> results = new ConcurrentHashMap<>();
    public void save(String tenantId, String resultId, Object result) { results.put(tenantId + ":" + resultId, result); }
    public Optional<Object> find(String tenantId, String resultId) { return Optional.ofNullable(results.get(tenantId + ":" + resultId)); }
}
