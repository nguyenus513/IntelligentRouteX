package com.routechain.api.v1.dto;

public record DispatchJobResponse(String jobId, String requestId, String tenantId, String status, String createdAt) { }
