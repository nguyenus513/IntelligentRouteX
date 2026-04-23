package com.routechain.v2.integration;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpForecastClientTest {
    private static final String LOADED_MODEL_FINGERPRINT = "sha256:chronos-fingerprint";

    @TempDir
    Path tempDir;

    @Test
    void happyPathSupportsDemandShiftZoneBurstAndPostDropShift() throws Exception {
        HttpServer server = HttpForecastTestSupport.server(Map.of(
                "/version", HttpForecastTestSupport.json(HttpForecastTestSupport.versionBody(
                        "v1",
                        "sha256:chronos",
                        true,
                        "materialized/chronos-2/model/chronos-runtime-manifest.json",
                        "HF_SNAPSHOT_PROMOTION",
                        LOADED_MODEL_FINGERPRINT)),
                "/ready", HttpForecastTestSupport.json(HttpForecastTestSupport.readyBody(true, "")),
                "/forecast/demand-shift", HttpForecastTestSupport.json(HttpForecastTestSupport.forecastBody(false, 0.71, null, 0.83, 90000L)),
                "/forecast/zone-burst", HttpForecastTestSupport.json(HttpForecastTestSupport.forecastBody(false, null, 0.74, 0.82, 80000L)),
                "/forecast/post-drop-shift", HttpForecastTestSupport.json(HttpForecastTestSupport.forecastBody(false, 0.69, null, 0.8, 85000L))));
        try {
            Path manifestPath = HttpForecastTestSupport.manifestV2(
                    tempDir,
                    "v1",
                    "sha256:chronos",
                    "dispatch-v2-ml/v1",
                    "dispatch-v2-java/v1",
                    LOADED_MODEL_FINGERPRINT);
            HttpForecastClient client = new HttpForecastClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(),
                    Duration.ofMillis(50),
                    Duration.ofMillis(100),
                    manifestPath);

            assertEquals("cuda:0", client.readyState().workerMetadata().device());
            assertEquals("fp16", client.readyState().workerMetadata().dtype());
            assertTrue(client.readyState().workerMetadata().modelLoaded());
            assertTrue(client.readyState().workerMetadata().warmupDone());

            ForecastResult demand = client.forecastDemandShift(demandShiftFeatureVector(), 100L);
            ForecastResult burst = client.forecastZoneBurst(zoneBurstFeatureVector(), 100L);
            ForecastResult postDrop = client.forecastPostDropShift(postDropShiftFeatureVector(), 100L);

            assertTrue(demand.applied());
            assertTrue(burst.applied());
            assertTrue(postDrop.applied());
        } finally {
            server.stop(0);
        }
    }

    private DemandShiftFeatureVector demandShiftFeatureVector() {
        return new DemandShiftFeatureVector("demand-shift-feature-vector/v1", "trace-forecast", "corridor-a", 3, 1, 2, 4.0, 5.0, 16.0, 0.68, 0.2, 30);
    }

    private ZoneBurstFeatureVector zoneBurstFeatureVector() {
        return new ZoneBurstFeatureVector("zone-burst-feature-vector/v1", "trace-forecast", "corridor-a", 3, 1, 2, 16.0, 0.68, 0.7, 0.64, 20);
    }

    private PostDropShiftFeatureVector postDropShiftFeatureVector() {
        return new PostDropShiftFeatureVector("post-drop-shift-feature-vector/v1", "trace-forecast", "corridor-a", 3, 1, 2, 16.0, 0.68, 0.72, 0.66, 45);
    }
}
