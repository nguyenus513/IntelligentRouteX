package com.routechain.api.v1.dto;

public record LiveSessionCreateRequest(String requestId, String tenantId, String cityId, String profile, RollingConfig rollingConfig) {
    public record RollingConfig(Integer cycleIntervalSeconds, Integer maxBufferWaitSeconds, Integer maxRuntimeMsPerCycle, Boolean freezeNextStop, Boolean freezePickedOrders, String adaptiveMlMode) { }
}
