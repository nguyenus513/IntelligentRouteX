package com.routechain.api.v1.dto;

import java.util.List;

public record DispatchJobRequest(
        String requestId,
        String tenantId,
        String profile,
        String datasetId,
        List<ApiDriverDto> drivers,
        List<ApiOrderDto> orders,
        AdaptiveMlOptions adaptiveMl,
        DispatchOptions options) {
    public record AdaptiveMlOptions(Boolean enabled, String mode, Integer topKMoves, Double explorationRate, Integer qualityBudgetMs) { }
    public record DispatchOptions(Integer maxRuntimeMs, Boolean returnDiagnostics) { }
    public record ApiOrderDto(String orderId, Double pickupLat, Double pickupLng, Double dropoffLat, Double dropoffLng, Integer demand, Integer readyTimeMinutes, Integer deadlineMinutes) { }
    public record ApiDriverDto(String driverId, Double lat, Double lng, Integer capacity) { }
}
