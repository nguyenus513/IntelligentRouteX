package com.routechain.api.v1.dto;

import java.util.List;

public record RescueJobRequest(String requestId, String tenantId, String reason, String affectedDriverId, List<String> affectedOrderIds, Options options) {
    public record Options(Boolean lateNotWorse, Integer maxRuntimeMs, String pdLnsMode) { }
}
