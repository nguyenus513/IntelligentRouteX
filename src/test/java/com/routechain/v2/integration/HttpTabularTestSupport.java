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

final class HttpTabularTestSupport {
    private HttpTabularTestSupport() {
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

    static Path manifestV1(Path tempDir,
                           String modelVersion,
                           String artifactDigest,
                           String compatibilityContractVersion,
                           String javaContractVersion) throws IOException {
        Path manifestPath = tempDir.resolve("model-manifest.yaml");
        Files.writeString(manifestPath, """
                schemaVersion: model-manifest/v1
                workers:
                  - worker_name: ml-tabular-worker
                    model_name: tabular-test
                    model_version: %s
                    artifact_digest: %s
                    rollback_artifact_digest: sha256:rollback
                    runtime_image: local/test
                    compatibility_contract_version: %s
                    min_supported_java_contract_version: %s
                    startup_warmup_request:
                      endpoint: /score/eta-residual
                      payload:
                        schemaVersion: score-request/v1
                        traceId: warmup-tabular
                """.formatted(modelVersion, artifactDigest, compatibilityContractVersion, javaContractVersion), StandardCharsets.UTF_8);
        return manifestPath;
    }

    static Path manifest(Path tempDir,
                         String modelVersion,
                         String artifactDigest,
                         String compatibilityContractVersion,
                         String javaContractVersion) throws IOException {
        return manifestV1(tempDir, modelVersion, artifactDigest, compatibilityContractVersion, javaContractVersion);
    }

    static Path manifestV2(Path tempDir,
                           String modelVersion,
                           String artifactDigest,
                           String compatibilityContractVersion,
                           String javaContractVersion,
                           String loadedModelFingerprint) throws IOException {
        Path manifestPath = tempDir.resolve("model-manifest.yaml");
        Files.writeString(manifestPath, """
                schemaVersion: model-manifest/v2
                workers:
                  - worker_name: ml-tabular-worker
                    model_name: tabular-test
                    model_version: %s
                    artifact_digest: %s
                    rollback_artifact_digest: sha256:rollback
                    runtime_image: local/test
                    compatibility_contract_version: %s
                    min_supported_java_contract_version: %s
                    local_model_root: materialized/tabular
                    local_artifact_path: materialized/tabular/model/tabular-runtime-manifest.json
                    materialization_mode: LOCAL_FILE_PROMOTION
                    ready_requires_local_load: true
                    offline_boot_supported: true
                    loaded_model_fingerprint: %s
                    startup_warmup_request:
                      endpoint: /score/eta-residual
                      payload:
                        schemaVersion: score-request/v1
                        traceId: warmup-tabular
                """.formatted(
                modelVersion,
                artifactDigest,
                compatibilityContractVersion,
                javaContractVersion,
                loadedModelFingerprint), StandardCharsets.UTF_8);
        return manifestPath;
    }

    static String versionBody(String modelVersion, String artifactDigest) {
        return versionBody(modelVersion, artifactDigest, true, "/tmp/materialized/tabular/model/tabular-runtime-manifest.json",
                "LOCAL_FILE_PROMOTION", "sha256:fingerprint");
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
                  "worker": "ml-tabular-worker",
                  "model": "tabular-test",
                  "modelVersion": "%s",
                  "artifactDigest": "%s",
                  "compatibilityContractVersion": "dispatch-v2-ml/v1",
                  "minSupportedJavaContractVersion": "dispatch-v2-java/v1",
                  "loadedFromLocal": %s,
                  "localArtifactPath": "%s",
                  "materializationMode": "%s",
                  "loadedModelFingerprint": "%s",
                  "device": "cpu",
                  "dtype": "fp32",
                  "gpuMemoryAllocatedMb": 0,
                  "batchSize": 16,
                  "compileMode": "eager",
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

    static String scoreBody(double score, double uncertainty) {
        return """
                {
                  "schemaVersion": "score-response/v1",
                  "traceId": "trace-test",
                  "sourceModel": "tabular-test",
                  "modelVersion": "v1",
                  "artifactDigest": "sha256:test",
                  "latencyMs": 5,
                  "fallbackUsed": false,
                  "payload": {
                    "score": %s,
                    "uncertainty": %s
                  }
                }
                """.formatted(Double.toString(score), Double.toString(uncertainty));
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
