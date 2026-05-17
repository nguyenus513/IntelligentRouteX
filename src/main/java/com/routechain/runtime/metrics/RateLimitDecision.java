package com.routechain.runtime.metrics;

import java.time.Instant;

public record RateLimitDecision(boolean allowed, String reason, Instant resetAt) { }
