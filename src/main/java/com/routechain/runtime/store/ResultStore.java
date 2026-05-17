package com.routechain.runtime.store;

import java.util.Optional;

public interface ResultStore {
    void save(String tenantId, String resultId, Object result);
    Optional<Object> find(String tenantId, String resultId);
}
