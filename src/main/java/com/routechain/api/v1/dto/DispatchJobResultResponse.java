package com.routechain.api.v1.dto;

import java.util.List;
import java.util.Map;

public record DispatchJobResultResponse(String jobId, String status, String finalSolver, Metrics metrics, List<?> routes, Map<String, Object> diagnostics) {
    public record Metrics(double coverageRate, double distanceKm, long lateCount, long runtimeMs) { }
}
