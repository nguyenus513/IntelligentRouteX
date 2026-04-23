package com.routechain.v2.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

public final class HttpGreedRlClient implements GreedRlClient {
    private static final String WORKER_NAME = "ml-greedrl-worker";
    private static final String ML_CONTRACT_VERSION = "dispatch-v2-ml/v1";
    private static final String JAVA_CONTRACT_VERSION = "dispatch-v2-java/v1";

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final URI baseUri;
    private final Duration readTimeout;
    private final WorkerReadyState readyState;

    public HttpGreedRlClient(String baseUrl,
                             Duration connectTimeout,
                             Duration readTimeout,
                             Path manifestPath) {
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                // Bundled uvicorn workers speak plain HTTP/1.1; Java's h2c upgrade attempt can break request framing.
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        this.objectMapper = JsonMapper.builder().findAndAddModules().build();
        this.baseUri = URI.create(baseUrl.endsWith("/") ? baseUrl : baseUrl + "/");
        this.readTimeout = readTimeout;
        this.readyState = bootstrapReadyState(manifestPath);
    }

    @Override
    public GreedRlBundleResult proposeBundles(GreedRlBundleFeatureVector featureVector, long timeoutBudgetMs) {
        if (!readyState.ready()) {
            return GreedRlBundleResult.notApplied("greedrl-worker-not-ready", readyState.workerMetadata());
        }
        try {
            HttpResponse<String> response = send("bundle/propose", featureVector, timeoutBudgetMs);
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                return GreedRlBundleResult.notApplied("greedrl-http-error", readyState.workerMetadata());
            }
            GreedRlResponse greedRlResponse = objectMapper.readValue(response.body(), GreedRlResponse.class);
            if (greedRlResponse.fallbackUsed()) {
                return GreedRlBundleResult.notApplied("greedrl-worker-fallback", metadataFrom(greedRlResponse));
            }
            if (greedRlResponse.payload() == null || greedRlResponse.payload().bundleProposals() == null) {
                return GreedRlBundleResult.notApplied("greedrl-malformed-payload", readyState.workerMetadata());
            }
            List<GreedRlBundleCandidate> proposals = greedRlResponse.payload().bundleProposals().stream()
                    .map(payload -> new GreedRlBundleCandidate(
                            payload.family(),
                            payload.orderIds() == null ? List.of() : List.copyOf(payload.orderIds()),
                            payload.acceptedBoundaryOrderIds() == null ? List.of() : List.copyOf(payload.acceptedBoundaryOrderIds()),
                            payload.boundaryCross(),
                            payload.traceReasons() == null ? List.of() : List.copyOf(payload.traceReasons())))
                    .toList();
            return GreedRlBundleResult.applied(proposals, metadataFrom(greedRlResponse));
        } catch (java.net.http.HttpTimeoutException exception) {
            return GreedRlBundleResult.notApplied("greedrl-timeout", readyState.workerMetadata());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return GreedRlBundleResult.notApplied("greedrl-interrupted", readyState.workerMetadata());
        } catch (IOException | RuntimeException exception) {
            return GreedRlBundleResult.notApplied("greedrl-unavailable", readyState.workerMetadata());
        }
    }

    @Override
    public GreedRlSequenceResult proposeSequence(GreedRlSequenceFeatureVector featureVector, long timeoutBudgetMs) {
        if (!readyState.ready()) {
            return GreedRlSequenceResult.notApplied("greedrl-worker-not-ready", readyState.workerMetadata());
        }
        try {
            HttpResponse<String> response = send("sequence/propose", featureVector, timeoutBudgetMs);
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                return GreedRlSequenceResult.notApplied("greedrl-http-error", readyState.workerMetadata());
            }
            GreedRlResponse greedRlResponse = objectMapper.readValue(response.body(), GreedRlResponse.class);
            if (greedRlResponse.fallbackUsed()) {
                return GreedRlSequenceResult.notApplied("greedrl-worker-fallback", metadataFrom(greedRlResponse));
            }
            if (greedRlResponse.payload() == null || greedRlResponse.payload().sequenceProposals() == null) {
                return GreedRlSequenceResult.notApplied("greedrl-malformed-payload", readyState.workerMetadata());
            }
            List<GreedRlSequenceProposal> proposals = greedRlResponse.payload().sequenceProposals().stream()
                    .map(payload -> new GreedRlSequenceProposal(
                            payload.stopOrder() == null ? List.of() : List.copyOf(payload.stopOrder()),
                            payload.sequenceScore(),
                            payload.traceReasons() == null ? List.of() : List.copyOf(payload.traceReasons())))
                    .toList();
            return GreedRlSequenceResult.applied(proposals, metadataFrom(greedRlResponse));
        } catch (java.net.http.HttpTimeoutException exception) {
            return GreedRlSequenceResult.notApplied("greedrl-timeout", readyState.workerMetadata());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return GreedRlSequenceResult.notApplied("greedrl-interrupted", readyState.workerMetadata());
        } catch (IOException | RuntimeException exception) {
            return GreedRlSequenceResult.notApplied("greedrl-unavailable", readyState.workerMetadata());
        }
    }

    @Override
    public WorkerReadyState readyState() {
        return readyState;
    }

    private HttpResponse<String> send(String path, Object payload, long timeoutBudgetMs) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(baseUri.resolve(path))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofMillis(Math.max(1L, Math.min(timeoutBudgetMs, readTimeout.toMillis()))))
                .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(
                        new GreedRlRequestEnvelope(
                                "greedrl-request/v1",
                                traceId(payload),
                                "bundle-pool",
                                timeoutBudgetMs,
                                ML_CONTRACT_VERSION,
                                payload))))
                .build();
        return httpClient.send(request, HttpResponse.BodyHandlers.ofString());
    }

    private WorkerReadyState bootstrapReadyState(Path manifestPath) {
        WorkerManifest manifest = new ModelManifestLoader().load(manifestPath);
        WorkerManifest.WorkerManifestEntry worker = manifest.worker(WORKER_NAME);
        if (worker == null) {
            return WorkerReadyState.notReady("manifest-worker-missing", MlWorkerMetadata.empty());
        }
        MlWorkerMetadata manifestMetadata = new MlWorkerMetadata(
                worker.modelName(),
                worker.modelVersion(),
                worker.artifactDigest(),
                0L);
        if (!ML_CONTRACT_VERSION.equals(worker.compatibilityContractVersion())) {
            return WorkerReadyState.notReady("ml-contract-incompatible", manifestMetadata);
        }
        if (!JAVA_CONTRACT_VERSION.equals(worker.minSupportedJavaContractVersion())) {
            return WorkerReadyState.notReady("java-contract-incompatible", manifestMetadata);
        }
        if (worker.artifactDigest() == null || worker.artifactDigest().isBlank() || worker.artifactDigest().contains("pending")) {
            return WorkerReadyState.notReady("artifact-not-pinned", manifestMetadata);
        }
        Duration bootstrapTimeout = Duration.ofMillis(Math.max(readTimeout.toMillis(), 15_000L));
        try {
            WorkerVersionResponse versionResponse = readJson("version", WorkerVersionResponse.class, bootstrapTimeout);
            if (!worker.modelVersion().equals(versionResponse.modelVersion())) {
                return WorkerReadyState.notReady("model-version-mismatch", manifestMetadata);
            }
            if (!worker.artifactDigest().equals(versionResponse.artifactDigest())) {
                return WorkerReadyState.notReady("artifact-digest-mismatch", manifestMetadata);
            }
            if (!ML_CONTRACT_VERSION.equals(versionResponse.compatibilityContractVersion())) {
                return WorkerReadyState.notReady("ml-contract-incompatible", manifestMetadata);
            }
            if (!JAVA_CONTRACT_VERSION.equals(versionResponse.minSupportedJavaContractVersion())) {
                return WorkerReadyState.notReady("java-contract-incompatible", manifestMetadata);
            }
            if (Boolean.TRUE.equals(worker.readyRequiresLocalLoad()) && !Boolean.TRUE.equals(versionResponse.loadedFromLocal())) {
                return WorkerReadyState.notReady("local-model-not-loaded", manifestMetadata);
            }
            if (Boolean.TRUE.equals(worker.readyRequiresLocalLoad())
                    && worker.loadedModelFingerprint() != null
                    && !worker.loadedModelFingerprint().isBlank()
                    && !worker.loadedModelFingerprint().equals(versionResponse.loadedModelFingerprint())) {
                return WorkerReadyState.notReady("loaded-model-fingerprint-mismatch", manifestMetadata);
            }
            WorkerReadyResponse readyResponse = readJson("ready", WorkerReadyResponse.class, bootstrapTimeout);
            if (!readyResponse.ready()) {
                return WorkerReadyState.notReady(
                        readyResponse.reason() == null || readyResponse.reason().isBlank() ? "worker-not-ready" : readyResponse.reason(),
                        manifestMetadata);
            }
            return WorkerReadyState.ready(new MlWorkerMetadata(
                    versionResponse.model(),
                    versionResponse.modelVersion(),
                    versionResponse.artifactDigest(),
                    0L,
                    blankToExpected(versionResponse.device(), ""),
                    blankToExpected(versionResponse.dtype(), ""),
                    versionResponse.gpuMemoryAllocatedMb(),
                    versionResponse.batchSize(),
                    blankToExpected(versionResponse.compileMode(), ""),
                    versionResponse.modelLoaded(),
                    versionResponse.warmupDone()));
        } catch (IOException | InterruptedException | RuntimeException exception) {
            if (exception instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            return WorkerReadyState.notReady("worker-unreachable", manifestMetadata);
        }
    }

    private <T> T readJson(String path, Class<T> type, Duration timeout) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(baseUri.resolve(path))
                .timeout(timeout)
                .GET()
                .build();
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IOException("Unexpected status " + response.statusCode() + " for " + path);
        }
        return objectMapper.readValue(response.body(), type);
    }

    private MlWorkerMetadata metadataFrom(GreedRlResponse response) {
        MlWorkerMetadata readyMetadata = readyState.workerMetadata();
        return new MlWorkerMetadata(
                blankToExpected(response.sourceModel(), readyMetadata.sourceModel()),
                blankToExpected(response.modelVersion(), readyMetadata.modelVersion()),
                blankToExpected(response.artifactDigest(), readyMetadata.artifactDigest()),
                response.latencyMs(),
                blankToExpected(response.device(), readyMetadata.device()),
                blankToExpected(response.dtype(), readyMetadata.dtype()),
                response.gpuMemoryAllocatedMb() > 0L ? response.gpuMemoryAllocatedMb() : readyMetadata.gpuMemoryAllocatedMb(),
                response.batchSize() > 0 ? response.batchSize() : readyMetadata.batchSize(),
                blankToExpected(response.compileMode(), readyMetadata.compileMode()),
                response.modelLoaded() || readyMetadata.modelLoaded(),
                response.warmupDone() || readyMetadata.warmupDone());
    }

    private String traceId(Object payload) {
        return switch (payload) {
            case GreedRlBundleFeatureVector value -> value.traceId();
            case GreedRlSequenceFeatureVector value -> value.traceId();
            default -> "unknown";
        };
    }

    private String blankToExpected(String candidate, String fallback) {
        return candidate == null || candidate.isBlank() ? fallback : candidate;
    }
}
