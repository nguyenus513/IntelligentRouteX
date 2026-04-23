package com.routechain.v2.integration;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpGreedRlClientTest {
    private static final String LOCAL_ARTIFACT_PATH = "materialized/greedrl/model/greedrl-runtime-manifest.json";
    private static final String LOADED_MODEL_FINGERPRINT = "sha256:greedrl-fingerprint";

    @TempDir
    Path tempDir;

    @Test
    void happyPathSupportsBundleAndSequenceProposal() throws Exception {
        HttpServer server = HttpGreedRlTestSupport.server(Map.of(
                "/version", HttpGreedRlTestSupport.json(HttpGreedRlTestSupport.versionBody(
                        "v1",
                        "sha256:greedrl",
                        true,
                        LOCAL_ARTIFACT_PATH,
                        "LOCAL_PACKAGE_PROMOTION",
                        LOADED_MODEL_FINGERPRINT)),
                "/ready", HttpGreedRlTestSupport.json(HttpGreedRlTestSupport.readyBody(true, "")),
                "/bundle/propose", HttpGreedRlTestSupport.json(HttpGreedRlTestSupport.bundleResponseBody(false)),
                "/sequence/propose", HttpGreedRlTestSupport.json(HttpGreedRlTestSupport.sequenceResponseBody(false))));
        try {
            Path manifestPath = HttpGreedRlTestSupport.manifestV2(
                    tempDir,
                    "v1",
                    "sha256:greedrl",
                    "dispatch-v2-ml/v1",
                    "dispatch-v2-java/v1",
                    LOADED_MODEL_FINGERPRINT);
            HttpGreedRlClient client = new HttpGreedRlClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(),
                    Duration.ofMillis(50),
                    Duration.ofMillis(100),
                    manifestPath);

            assertEquals("cuda:0", client.readyState().workerMetadata().device());
            assertEquals("fp16", client.readyState().workerMetadata().dtype());
            assertTrue(client.readyState().workerMetadata().modelLoaded());
            assertTrue(client.readyState().workerMetadata().warmupDone());

            GreedRlBundleResult bundleResult = client.proposeBundles(bundleFeatureVector(), 100L);
            GreedRlSequenceResult sequenceResult = client.proposeSequence(sequenceFeatureVector(), 100L);

            assertTrue(bundleResult.applied());
            assertTrue(sequenceResult.applied());
            assertEquals(List.of("order-1", "order-2", "order-3"), bundleResult.proposals().getFirst().orderIds());
            assertEquals(List.of("order-1", "order-3", "order-2"), sequenceResult.sequences().getFirst().stopOrder());
        } finally {
            server.stop(0);
        }
    }

    private GreedRlBundleFeatureVector bundleFeatureVector() {
        return new GreedRlBundleFeatureVector(
                "greedrl-bundle-feature-vector/v1",
                "trace-greedrl",
                "cluster-1",
                List.of("order-1", "order-2", "order-3"),
                List.of("order-1", "order-2", "order-3"),
                List.of("order-3"),
                Map.of("order-1", 0.8, "order-2", 0.7, "order-3", 0.6),
                3,
                2);
    }

    private GreedRlSequenceFeatureVector sequenceFeatureVector() {
        return new GreedRlSequenceFeatureVector(
                "greedrl-sequence-feature-vector/v1",
                "trace-greedrl",
                "cluster-1",
                "bundle-1",
                List.of("order-1", "order-2", "order-3"),
                "order-1",
                "driver-1",
                2);
    }
}
