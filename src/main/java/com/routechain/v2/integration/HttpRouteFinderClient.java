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

public final class HttpRouteFinderClient implements RouteFinderClient {
    private static final String WORKER_NAME = "ml-routefinder-worker";
    private static final String ML_CONTRACT_VERSION = "dispatch-v2-ml/v1";
    private static final String JAVA_CONTRACT_VERSION = "dispatch-v2-java/v1";

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final URI baseUri;
    private final Duration readTimeout;
    private final WorkerReadyState readyState;

    public HttpRouteFinderClient(String baseUrl,
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
    public RouteFinderResult refineRoute(RouteFinderFeatureVector featureVector, long timeoutBudgetMs) {
        return invoke("route/refine", featureVector, timeoutBudgetMs);
    }

    @Override
    public RouteFinderResult generateAlternatives(RouteFinderFeatureVector featureVector, long timeoutBudgetMs) {
        return invoke("route/alternatives", featureVector, timeoutBudgetMs);
    }

    @Override
    public WorkerReadyState readyState() {
        return readyState;
    }

    private RouteFinderResult invoke(String path, RouteFinderFeatureVector featureVector, long timeoutBudgetMs) {
        if (!readyState.ready()) {
            return RouteFinderResult.notApplied("routefinder-worker-not-ready", readyState.workerMetadata());
        }
        try {
            HttpRequest request = HttpRequest.newBuilder(baseUri.resolve(path))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofMillis(Math.max(1L, Math.min(timeoutBudgetMs, readTimeout.toMillis()))))
                    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(
                            new RouteFinderRequestEnvelope(
                                    "route-request/v1",
                                    featureVector.traceId(),
                                    "route-proposal-pool",
                                    timeoutBudgetMs,
                                    ML_CONTRACT_VERSION,
                                    featureVector))))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                return RouteFinderResult.notApplied("routefinder-http-error", readyState.workerMetadata());
            }
            RouteFinderResponse routeFinderResponse = objectMapper.readValue(response.body(), RouteFinderResponse.class);
            if (routeFinderResponse.payload() == null || routeFinderResponse.payload().routes() == null) {
                return RouteFinderResult.notApplied("routefinder-malformed-payload", readyState.workerMetadata());
            }
            MlWorkerMetadata workerMetadata = metadataFromResponse(
                    routeFinderResponse.sourceModel(),
                    routeFinderResponse.modelVersion(),
                    routeFinderResponse.artifactDigest(),
                    routeFinderResponse.latencyMs(),
                    routeFinderResponse.device(),
                    routeFinderResponse.dtype(),
                    routeFinderResponse.gpuMemoryAllocatedMb(),
                    routeFinderResponse.batchSize(),
                    routeFinderResponse.compileMode(),
                    routeFinderResponse.modelLoaded(),
                    routeFinderResponse.warmupDone());
            if (routeFinderResponse.fallbackUsed()) {
                return RouteFinderResult.notApplied("routefinder-worker-fallback", workerMetadata);
            }
            return RouteFinderResult.applied(
                    routeFinderResponse.payload().routes().stream()
                            .map(route -> new RouteFinderRoute(
                                    List.copyOf(route.stopOrder()),
                                    route.projectedPickupEtaMinutes(),
                                    route.projectedCompletionEtaMinutes(),
                                    route.routeScore(),
                                    route.traceReasons() == null ? List.of() : List.copyOf(route.traceReasons())))
                            .toList(),
                    false,
                    workerMetadata);
        } catch (java.net.http.HttpTimeoutException exception) {
            return RouteFinderResult.notApplied("routefinder-timeout", readyState.workerMetadata());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return RouteFinderResult.notApplied("routefinder-interrupted", readyState.workerMetadata());
        } catch (IOException | RuntimeException exception) {
            return RouteFinderResult.notApplied("routefinder-unavailable", readyState.workerMetadata());
        }
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

    private String blankToExpected(String candidate, String fallback) {
        return candidate == null || candidate.isBlank() ? fallback : candidate;
    }

    private MlWorkerMetadata metadataFromResponse(String sourceModel,
                                                  String modelVersion,
                                                  String artifactDigest,
                                                  long latencyMs,
                                                  String device,
                                                  String dtype,
                                                  long gpuMemoryAllocatedMb,
                                                  int batchSize,
                                                  String compileMode,
                                                  boolean modelLoaded,
                                                  boolean warmupDone) {
        MlWorkerMetadata readyMetadata = readyState.workerMetadata();
        return new MlWorkerMetadata(
                blankToExpected(sourceModel, readyMetadata.sourceModel()),
                blankToExpected(modelVersion, readyMetadata.modelVersion()),
                blankToExpected(artifactDigest, readyMetadata.artifactDigest()),
                latencyMs,
                blankToExpected(device, readyMetadata.device()),
                blankToExpected(dtype, readyMetadata.dtype()),
                gpuMemoryAllocatedMb > 0L ? gpuMemoryAllocatedMb : readyMetadata.gpuMemoryAllocatedMb(),
                batchSize > 0 ? batchSize : readyMetadata.batchSize(),
                blankToExpected(compileMode, readyMetadata.compileMode()),
                modelLoaded || readyMetadata.modelLoaded(),
                warmupDone || readyMetadata.warmupDone());
    }
}
