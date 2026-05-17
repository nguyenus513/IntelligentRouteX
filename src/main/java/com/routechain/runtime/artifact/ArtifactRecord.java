package com.routechain.runtime.artifact;

import java.time.Instant;

public record ArtifactRecord(String artifactId, String tenantId, String jobId, String type, String path, Instant createdAt, int retentionDays) { }
