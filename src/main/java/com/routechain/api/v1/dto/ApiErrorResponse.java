package com.routechain.api.v1.dto;

import java.util.Map;

public record ApiErrorResponse(String code, String message, Map<String, Object> details) { }
