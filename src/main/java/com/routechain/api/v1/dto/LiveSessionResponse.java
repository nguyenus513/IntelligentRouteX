package com.routechain.api.v1.dto;

public record LiveSessionResponse(String sessionId, String requestId, String tenantId, String status, String createdAt) { }
