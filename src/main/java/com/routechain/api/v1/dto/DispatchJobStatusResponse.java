package com.routechain.api.v1.dto;

public record DispatchJobStatusResponse(String jobId, String requestId, String tenantId, String status, String createdAt, String completedAt, String error) { }
