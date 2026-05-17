package com.routechain.api.v1.dto;

public record DriverTelemetryRequest(String requestId, String tenantId, Double lat, Double lng, String actionState, String activeOrderId) { }
