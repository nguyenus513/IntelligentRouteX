package com.routechain.runtime.store;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryLiveSessionStore implements LiveSessionStore {
    private final Map<String, RuntimeLiveSessionRecord> sessions = new ConcurrentHashMap<>();
    public RuntimeLiveSessionRecord save(RuntimeLiveSessionRecord session) { sessions.put(key(session.tenantId(), session.sessionId()), session); return session; }
    public Optional<RuntimeLiveSessionRecord> find(String tenantId, String sessionId) { return Optional.ofNullable(sessions.get(key(tenantId, sessionId))); }
    private String key(String tenantId, String sessionId) { return tenantId + ":" + sessionId; }
}
