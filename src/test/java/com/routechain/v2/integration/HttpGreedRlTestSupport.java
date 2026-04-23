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

final class HttpGreedRlTestSupport {
    private HttpGreedRlTestSupport() {
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
        Path manifestPath = tempDir.resolve("greedrl-model-manifest.yaml");
        Files.writeString(manifestPath, """
                schemaVersion: model-manifest/v1
                workers:
                  - worker_name: ml-greedrl-worker
                    model_name: greedrl-local
                    model_version: %s
                    artifact_digest: %s
                    rollback_artifact_digest: sha256:rollback
                    runtime_image: local/test
                    compatibility_contract_version: %s
                    min_supported_java_contract_version: %s
                    startup_warmup_request:
                      endpoint: /bundle/propose
                      payload:
                        schemaVersion: greedrl-request/v1
                        traceId: warmup-greedrl
                        payload:
                          schemaVersion: greedrl-bundle-feature-vector/v1
                          traceId: warmup-greedrl
                          clusterId: cluster-1
                          workingOrderIds:
                            - order-1
                            - order-2
                            - order-3
                          prioritizedOrderIds:
                            - order-1
                            - order-2
                            - order-3
                          acceptedBoundaryOrderIds:
                            - order-3
                          supportScoreByOrder:
                            order-1: 0.8
                            order-2: 0.7
                            order-3: 0.6
                          bundleMaxSize: 3
                          maxProposals: 2
                """.formatted(modelVersion, artifactDigest, compatibilityContractVersion, javaContractVersion), StandardCharsets.UTF_8);
        return manifestPath;
    }

    static Path manifestV2(Path tempDir,
                           String modelVersion,
                           String artifactDigest,
                           String compatibilityContractVersion,
                           String javaContractVersion,
                           String loadedModelFingerprint) throws IOException {
        Path manifestPath = tempDir.resolve("greedrl-model-manifest-v2.yaml");
        Files.writeString(manifestPath, """
                schemaVersion: model-manifest/v2
                workers:
                  - worker_name: ml-greedrl-worker
                    model_name: greedrl-local
                    model_version: %s
                    artifact_digest: %s
                    rollback_artifact_digest: sha256:rollback
                    runtime_image: local/test
                    compatibility_contract_version: %s
                    min_supported_java_contract_version: %s
                    local_model_root: materialized/greedrl
                    local_artifact_path: materialized/greedrl/model/greedrl-runtime-manifest.json
                    materialization_mode: LOCAL_PACKAGE_PROMOTION
                    ready_requires_local_load: true
                    offline_boot_supported: true
                    loaded_model_fingerprint: %s
                    source_repository: https://huggingface.co/Cainiao-AI/GreedRL
                    source_ref: 2d5d3bde195dbb5f602908fe42170ffd3ee25c75
                    source_package_requirement: greedrl-community-edition
                    source_python_requirement: ==3.8.*
                    source_build_command: python setup.py build
                    source_test_command: python -c "import greedrl"
                    startup_warmup_request:
                      endpoint: /bundle/propose
                      payload:
                        schemaVersion: greedrl-request/v1
                        traceId: warmup-greedrl
                        payload:
                          schemaVersion: greedrl-bundle-feature-vector/v1
                          traceId: warmup-greedrl
                          clusterId: cluster-1
                          workingOrderIds:
                            - order-1
                            - order-2
                            - order-3
                          prioritizedOrderIds:
                            - order-1
                            - order-2
                            - order-3
                          acceptedBoundaryOrderIds:
                            - order-3
                          supportScoreByOrder:
                            order-1: 0.8
                            order-2: 0.7
                            order-3: 0.6
                          bundleMaxSize: 3
                          maxProposals: 2
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
                  "worker": "ml-greedrl-worker",
                  "model": "greedrl-local",
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
                  "gpuMemoryAllocatedMb": 5120,
                  "batchSize": 6,
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

    static String bundleResponseBody(boolean fallbackUsed) {
        return """
                {
                  "schemaVersion": "greedrl-response/v1",
                  "traceId": "trace-greedrl",
                  "sourceModel": "greedrl-local",
                  "modelVersion": "v1",
                  "artifactDigest": "sha256:greedrl",
                  "latencyMs": 9,
                  "fallbackUsed": %s,
                  "payload": {
                    "bundleProposals": [
                      {
                        "family": "COMPACT_CLIQUE",
                        "orderIds": ["order-1", "order-2", "order-3"],
                        "acceptedBoundaryOrderIds": ["order-3"],
                        "boundaryCross": true,
                        "traceReasons": ["greedrl-bundle-proposal"]
                      }
                    ],
                    "sequenceProposals": []
                  }
                }
                """.formatted(Boolean.toString(fallbackUsed));
    }

    static String sequenceResponseBody(boolean fallbackUsed) {
        return """
                {
                  "schemaVersion": "greedrl-response/v1",
                  "traceId": "trace-greedrl",
                  "sourceModel": "greedrl-local",
                  "modelVersion": "v1",
                  "artifactDigest": "sha256:greedrl",
                  "latencyMs": 9,
                  "fallbackUsed": %s,
                  "payload": {
                    "bundleProposals": [],
                    "sequenceProposals": [
                      {
                        "stopOrder": ["order-1", "order-3", "order-2"],
                        "sequenceScore": 0.73,
                        "traceReasons": ["greedrl-sequence-proposal"]
                      }
                    ]
                  }
                }
                """.formatted(Boolean.toString(fallbackUsed));
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
