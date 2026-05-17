package com.routechain.api.v1.dto;

import java.util.List;
import java.util.Map;

public record LiveSessionStateResponse(String sessionId, String tenantId, String status, int bufferedOrders, int assignedOrders, List<?> activeRoutes, List<Map<String, Object>> cycleHistory) { }
