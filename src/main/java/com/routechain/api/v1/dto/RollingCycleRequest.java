package com.routechain.api.v1.dto;

public record RollingCycleRequest(String requestId, String tenantId, Boolean returnDiagnostics, String pdLnsMode) { }
