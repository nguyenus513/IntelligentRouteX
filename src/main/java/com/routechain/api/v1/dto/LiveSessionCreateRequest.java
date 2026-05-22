package com.routechain.api.v1.dto;

import java.util.List;

public record LiveSessionCreateRequest(String requestId, String tenantId, String cityId, String profile, RollingConfig rollingConfig, List<DispatchJobRequest.ApiDriverDto> drivers) {
    public record RollingConfig(Integer cycleIntervalSeconds, Integer maxBufferWaitSeconds, Integer maxRuntimeMsPerCycle, Boolean freezeNextStop, Boolean freezePickedOrders, String adaptiveMlMode) { }
}
