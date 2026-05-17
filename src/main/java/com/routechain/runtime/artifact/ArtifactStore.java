package com.routechain.runtime.artifact;

import java.util.List;
import java.util.Optional;

public interface ArtifactStore {
    ArtifactRecord save(ArtifactRecord artifact);
    Optional<ArtifactRecord> find(String artifactId);
    List<ArtifactRecord> listForJob(String tenantId, String jobId);
}
