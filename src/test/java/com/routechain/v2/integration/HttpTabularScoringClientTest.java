package com.routechain.v2.integration;

import com.sun.net.httpserver.HttpServer;
import com.routechain.v2.cluster.PairFeatureVector;
import com.routechain.v2.context.EtaFeatureVector;
import com.routechain.v2.route.DriverFitFeatureVector;
import com.routechain.v2.route.RouteValueFeatureVector;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpTabularScoringClientTest {

    @TempDir
    Path tempDir;

    @Test
    void happyPathSupportsEtaPairDriverFitAndRouteValue() throws Exception {
        HttpServer server = HttpTabularTestSupport.server(Map.of(
                "/version", HttpTabularTestSupport.json(HttpTabularTestSupport.versionBody(
                        "v1",
                        "sha256:test",
                        true,
                        "/tmp/materialized/tabular/model/tabular-runtime-manifest.json",
                        "LOCAL_FILE_PROMOTION",
                        "sha256:fingerprint")),
                "/ready", HttpTabularTestSupport.json(HttpTabularTestSupport.readyBody(true, "")),
                "/score/eta-residual", HttpTabularTestSupport.json(HttpTabularTestSupport.scoreBody(0.2, 0.1)),
                "/score/pair", HttpTabularTestSupport.json(HttpTabularTestSupport.scoreBody(0.2, 0.1)),
                "/score/driver-fit", HttpTabularTestSupport.json(HttpTabularTestSupport.scoreBody(0.2, 0.1)),
                "/score/route-value", HttpTabularTestSupport.json(HttpTabularTestSupport.scoreBody(0.2, 0.1))));
        try {
            Path manifestPath = HttpTabularTestSupport.manifestV2(
                    tempDir,
                    "v1",
                    "sha256:test",
                    "dispatch-v2-ml/v1",
                    "dispatch-v2-java/v1",
                    "sha256:fingerprint");
            HttpTabularScoringClient client = new HttpTabularScoringClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(),
                    Duration.ofMillis(50),
                    Duration.ofMillis(100),
                    manifestPath);

            assertEquals("cpu", client.readyState().workerMetadata().device());
            assertEquals("fp32", client.readyState().workerMetadata().dtype());
            assertTrue(client.readyState().workerMetadata().modelLoaded());
            assertTrue(client.readyState().workerMetadata().warmupDone());

            List<TabularScoreResult> results = List.of(
                    client.scoreEtaResidual(new EtaFeatureVector("eta-feature-vector/v1", 5.0, 1.0, 1.0, 2.0, 12), 100L),
                    client.scorePair(new PairFeatureVector("pair-feature-vector/v1", "o1", "o2", 1.0, 2.0, 3L, 10.0, true, 1.1, 0.9, false), 100L),
                    client.scoreDriverFit(new DriverFitFeatureVector("driver-fit-feature-vector/v1", "trace", "bundle", "anchor", "driver", 5.0, 0.2, 0.7, 0.8, 0.6, 0.5, 0.1, 0.0, 0.7), 100L),
                    client.scoreRouteValue(new RouteValueFeatureVector("route-value-feature-vector/v1", "trace", "proposal", "bundle", "anchor", "driver", "HEURISTIC_FAST", 5.0, 15.0, 0.7, 0.8, 0.6, 0.5, 0.4, 0.1, 0.0, 0.0), 100L));

            assertTrue(results.stream().allMatch(TabularScoreResult::applied));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void fingerprintMismatchLeavesWorkerNotReady() throws Exception {
        HttpServer server = HttpTabularTestSupport.server(Map.of(
                "/version", HttpTabularTestSupport.json(HttpTabularTestSupport.versionBody(
                        "v1",
                        "sha256:test",
                        true,
                        "/tmp/materialized/tabular/model/tabular-runtime-manifest.json",
                        "LOCAL_FILE_PROMOTION",
                        "sha256:other")),
                "/ready", HttpTabularTestSupport.json(HttpTabularTestSupport.readyBody(true, ""))));
        try {
            Path manifestPath = HttpTabularTestSupport.manifestV2(
                    tempDir,
                    "v1",
                    "sha256:test",
                    "dispatch-v2-ml/v1",
                    "dispatch-v2-java/v1",
                    "sha256:fingerprint");
            HttpTabularScoringClient client = new HttpTabularScoringClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(),
                    Duration.ofMillis(50),
                    Duration.ofMillis(100),
                    manifestPath);

            assertFalse(client.readyState().ready());
            assertEquals("loaded-model-fingerprint-mismatch", client.readyState().reason());
        } finally {
            server.stop(0);
        }
    }
}
