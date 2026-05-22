package com.routechain.api.v1.dto;

import java.util.List;
import java.util.Map;

public record LiveSessionStateResponse(String sessionId, String tenantId, String status, int bufferedOrders, int assignedOrders, List<?> activeRoutes, List<Map<String, Object>> cycleHistory, Object decisionTrace, List<Map<String, Object>> bufferItems, List<DispatchJobRequest.ApiDriverDto> drivers, List<Map<String, Object>> driverStates, List<Map<String, Object>> completedOrders, Map<String, Object> removedMarkers, List<Map<String, Object>> consoleTrace, Map<String, Object> bufferMonitor) { }
