package com.routechain.api.v1.dto;

public record DispatchJobResponse(String jobId, String requestId, String tenantId, String status, String createdAt, String executionId) {
    public DispatchJobResponse(String jobId, String requestId, String tenantId, String status, String createdAt) {
        this(jobId, requestId, tenantId, status, createdAt, jobId == null ? null : "exec_" + jobId);
    }
}
