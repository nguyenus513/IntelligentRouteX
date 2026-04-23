package com.routechain.v2.integration;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;

final class HttpRouteFinderTestSupport {
    private HttpRouteFinderTestSupport() {
    }

    static HttpServer server(Map<String, HttpHandler> handlers) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        for (Map.Entry<String, HttpHandler> entry : handlers.entrySet()) {
            server.createContext(entry.getKey(), entry.getValue());
        }
        server.start();
        return server;
    }

    static HttpHandler json(String body) {
        return exchange -> write(exchange, 200, body);
    }

    static HttpHandler status(int statusCode, String body) {
        return exchange -> write(exchange, statusCode, body);
    }

    static HttpHandler delayed(Duration delay, String body) {
        return exchange -> {
            try {
                Thread.sleep(delay.toMillis());
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
            write(exchange, 200, body);
        };
    }

    static Path manifest(Path tempDir,
                         String modelVersion,
                         String artifactDigest,
                         String compatibilityContractVersion,
                         String javaContractVersion) throws IOException {
        return manifestV1(tempDir, modelVersion, artifactDigest, compatibilityContractVersion, javaContractVersion);
    }

    static Path manifestV1(Path tempDir,
                           String modelVersion,
                           String artifactDigest,
                           String compatibilityContractVersion,
                           String javaContractVersion) throws IOException {
        Path manifestPath = tempDir.resolve("routefinder-model-manifest.yaml");
        Files.writeString(manifestPath, """
                schemaVersion: model-manifest/v1
                workers:
                  - worker_name: ml-routefinder-worker
                    model_name: routefinder-local
                    model_version: %s
                    artifact_digest: %s
                    rollback_artifact_digest: sha256:rollback
                    runtime_image: local/test
                    compatibility_contract_version: %s
                    min_supported_java_contract_version: %s
                    startup_warmup_request:
                      endpoint: /route/refine
                      payload:
                        schemaVersion: route-request/v1
                        traceId: warmup-routefinder
                        payload:
                          schemaVersion: routefinder-feature-vector/v1
                          traceId: warmup-routefinder
                          bundleId: bundle-1
                          anchorOrderId: order-1
                          driverId: driver-1
                          baselineSource: HEURISTIC_FAST
                          baselineStopOrder:
                            - order-1
                            - order-2
                            - order-3
                          bundleOrderIds:
                            - order-1
                            - order-2
                            - order-3
                          projectedPickupEtaMinutes: 5.0
                          projectedCompletionEtaMinutes: 18.0
                          rerankScore: 0.7
                          bundleScore: 0.8
                          anchorScore: 0.75
                          averagePairSupport: 0.65
                          boundaryCross: false
                          maxAlternatives: 2
                """.formatted(modelVersion, artifactDigest, compatibilityContractVersion, javaContractVersion), StandardCharsets.UTF_8);
        return manifestPath;
    }

    static Path manifestV2(Path tempDir,
                           String modelVersion,
                           String artifactDigest,
                           String compatibilityContractVersion,
                           String javaContractVersion,
                           String loadedModelFingerprint) throws IOException {
        Path manifestPath = tempDir.resolve("routefinder-model-manifest-v2.yaml");
        Files.writeString(manifestPath, """
                schemaVersion: model-manifest/v2
                workers:
                  - worker_name: ml-routefinder-worker
                    model_name: routefinder-local
                    model_version: %s
                    artifact_digest: %s
                    rollback_artifact_digest: sha256:rollback
                    runtime_image: local/test
                    compatibility_contract_version: %s
                    min_supported_java_contract_version: %s
                    local_model_root: materialized/routefinder
                    local_artifact_path: materialized/routefinder/model/routefinder-model.json
                    materialization_mode: HF_CHECKPOINT_PROMOTION
                    ready_requires_local_load: true
                    offline_boot_supported: true
                    loaded_model_fingerprint: %s
                    source_repository: https://github.com/ai4co/routefinder.git
                    source_ref: fe0e45b6df118af03c5f42db8b93a351f7629131
                    source_checkpoint_path: checkpoints/100/rf-transformer.ckpt
                    source_download_command: python scripts/download_hf.py --models --no-data
                    source_test_command: python test.py --checkpoint checkpoints/100/rf-transformer.ckpt
                    startup_warmup_request:
                      endpoint: /route/refine
                      payload:
                        schemaVersion: route-request/v1
                        traceId: warmup-routefinder
                        payload:
                          schemaVersion: routefinder-feature-vector/v1
                          traceId: warmup-routefinder
                          bundleId: bundle-1
                          anchorOrderId: order-1
                          driverId: driver-1
                          baselineSource: HEURISTIC_FAST
                          baselineStopOrder:
                            - order-1
                            - order-2
                            - order-3
                          bundleOrderIds:
                            - order-1
                            - order-2
                            - order-3
                          projectedPickupEtaMinutes: 5.0
                          projectedCompletionEtaMinutes: 18.0
                          rerankScore: 0.7
                          bundleScore: 0.8
                          anchorScore: 0.75
                          averagePairSupport: 0.65
                          boundaryCross: false
                          maxAlternatives: 2
                """.formatted(modelVersion, artifactDigest, compatibilityContractVersion, javaContractVersion, loadedModelFingerprint), StandardCharsets.UTF_8);
        return manifestPath;
    }

    static String versionBody(String modelVersion, String artifactDigest) {
        return versionBody(modelVersion, artifactDigest, false, "", "", "");
    }

    static String versionBody(String modelVersion,
                              String artifactDigest,
                              boolean loadedFromLocal,
                              String localArtifactPath,
                              String materializationMode,
                              String loadedModelFingerprint) {
        return """
                {
                  "schemaVersion": "worker-version/v1",
                  "worker": "ml-routefinder-worker",
                  "model": "routefinder-local",
                  "modelVersion": "%s",
                  "artifactDigest": "%s",
                  "compatibilityContractVersion": "dispatch-v2-ml/v1",
                  "minSupportedJavaContractVersion": "dispatch-v2-java/v1",
                  "loadedFromLocal": %s,
                  "localArtifactPath": "%s",
                  "materializationMode": "%s",
                  "loadedModelFingerprint": "%s",
                  "device": "cuda:0",
                  "dtype": "fp16",
                  "gpuMemoryAllocatedMb": 6144,
                  "batchSize": 4,
                  "compileMode": "inductor",
                  "modelLoaded": true,
                  "warmupDone": true
                }
                """.formatted(
                modelVersion,
                artifactDigest,
                Boolean.toString(loadedFromLocal),
                localArtifactPath,
                materializationMode,
                loadedModelFingerprint);
    }

    static String readyBody(boolean ready, String reason) {
        return """
                {
                  "schemaVersion": "worker-ready/v1",
                  "ready": %s,
                  "reason": "%s"
                }
                """.formatted(Boolean.toString(ready), reason);
    }

    static String routeBody(String reason) {
        return """
                {
                  "schemaVersion": "routefinder-response/v1",
                  "traceId": "trace-test",
                  "sourceModel": "routefinder-local",
                  "modelVersion": "v1",
                  "artifactDigest": "sha256:routefinder",
                  "latencyMs": 7,
                  "fallbackUsed": false,
                  "payload": {
                    "routes": [
                      {
                        "stopOrder": ["order-1", "order-3", "order-2"],
                        "projectedPickupEtaMinutes": 4.5,
                        "projectedCompletionEtaMinutes": 16.5,
                        "routeScore": 0.77,
                        "traceReasons": ["%s"]
                      }
                    ]
                  }
                }
                """.formatted(reason);
    }

    private static void write(HttpExchange exchange, int statusCode, String body) throws IOException {
        exchange.getRequestBody().readAllBytes();
        byte[] responseBytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(statusCode, responseBytes.length);
        exchange.getResponseBody().write(responseBytes);
        exchange.close();
    }
}
