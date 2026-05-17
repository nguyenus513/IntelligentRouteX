package com.routechain.runtime.artifact;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class FileSystemArtifactStore implements ArtifactStore {
    private final Map<String, ArtifactRecord> artifacts = new ConcurrentHashMap<>();
    public ArtifactRecord save(ArtifactRecord artifact) { artifacts.put(artifact.artifactId(), artifact); return artifact; }
    public Optional<ArtifactRecord> find(String artifactId) { return Optional.ofNullable(artifacts.get(artifactId)); }
    public List<ArtifactRecord> listForJob(String tenantId, String jobId) { return artifacts.values().stream().filter(a -> a.tenantId().equals(tenantId) && a.jobId().equals(jobId)).toList(); }
}
