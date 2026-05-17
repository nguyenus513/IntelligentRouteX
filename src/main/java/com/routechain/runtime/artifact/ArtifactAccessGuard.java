package com.routechain.runtime.artifact;

public final class ArtifactAccessGuard {
    public boolean canRead(String tenantId, ArtifactRecord artifact) { return artifact != null && artifact.tenantId().equals(tenantId); }
}
