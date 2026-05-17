package com.routechain.runtime.store;

import java.util.Optional;

public interface LiveSessionStore {
    RuntimeLiveSessionRecord save(RuntimeLiveSessionRecord session);
    Optional<RuntimeLiveSessionRecord> find(String tenantId, String sessionId);
}
