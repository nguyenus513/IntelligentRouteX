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

class HttpRouteFinderClientTest {
    private static final String LOADED_MODEL_FINGERPRINT = "sha256:8b52802e0e685f7ae36aa62940ca848042ad81341d55dda36190e90a9e7b10fe";

    @TempDir
    Path tempDir;

    @Test
    void happyPathSupportsRefineAndAlternatives() throws Exception {
        HttpServer server = HttpRouteFinderTestSupport.server(Map.of(
                "/version", HttpRouteFinderTestSupport.json(HttpRouteFinderTestSupport.versionBody(
                        "v1",
                        "sha256:routefinder",
                        true,
                        "materialized/routefinder/model/routefinder-model.json",
                        "LOCAL_FILE",
                        LOADED_MODEL_FINGERPRINT)),
                "/ready", HttpRouteFinderTestSupport.json(HttpRouteFinderTestSupport.readyBody(true, "")),
                "/route/refine", HttpRouteFinderTestSupport.json(HttpRouteFinderTestSupport.routeBody("routefinder-refined")),
                "/route/alternatives", HttpRouteFinderTestSupport.json(HttpRouteFinderTestSupport.routeBody("routefinder-alternative"))));
        try {
            Path manifestPath = HttpRouteFinderTestSupport.manifestV2(
                    tempDir,
                    "v1",
                    "sha256:routefinder",
                    "dispatch-v2-ml/v1",
                    "dispatch-v2-java/v1",
                    LOADED_MODEL_FINGERPRINT);
            HttpRouteFinderClient client = new HttpRouteFinderClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(),
                    Duration.ofMillis(50),
                    Duration.ofMillis(100),
                    manifestPath);

            assertEquals("cuda:0", client.readyState().workerMetadata().device());
            assertEquals("fp16", client.readyState().workerMetadata().dtype());
            assertTrue(client.readyState().workerMetadata().modelLoaded());
            assertTrue(client.readyState().workerMetadata().warmupDone());

            RouteFinderFeatureVector featureVector = featureVector();
            List<RouteFinderResult> results = List.of(
                    client.generateAlternatives(featureVector, 100L),
                    client.refineRoute(featureVector, 100L));

            assertTrue(results.stream().allMatch(RouteFinderResult::applied));
            assertEquals(List.of("order-1", "order-3", "order-2"), results.getFirst().routes().getFirst().stopOrder());
        } finally {
            server.stop(0);
        }
    }

    private RouteFinderFeatureVector featureVector() {
        return new RouteFinderFeatureVector(
                "routefinder-feature-vector/v1",
                "trace-test",
                "bundle-1",
                "order-1",
                "driver-1",
                "HEURISTIC_FAST",
                List.of("order-1", "order-2", "order-3"),
                List.of("order-1", "order-2", "order-3"),
                5.0,
                18.0,
                0.7,
                0.8,
                0.75,
                0.65,
                false,
                2);
    }
}
