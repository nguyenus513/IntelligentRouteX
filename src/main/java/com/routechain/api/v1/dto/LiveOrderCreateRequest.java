package com.routechain.api.v1.dto;

public record LiveOrderCreateRequest(String requestId, String tenantId, DispatchJobRequest.ApiOrderDto order) { }
