package com.routechain.v2.harvest;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.decision.DecisionStageInputV1;
import com.routechain.v2.decision.DecisionStageName;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertTrue;

class HarvestRecorderTest {

    @Test
    void recordDecisionStageInputEmitsObservationRowsWithProvenance() throws Exception {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        Path bronzeDir = Files.createTempDirectory("dispatch-v2-harvest-recorder");
        properties.getHarvest().setBaseDir(bronzeDir.toString());

        try (HarvestRailWriter writer = new HarvestRailWriter(properties)) {
            HarvestRecorder recorder = new HarvestRecorder(
                    properties,
                    writer,
                    new HarvestRuntimeMetadataResolver(properties));
            DecisionStageInputV1 input = new DecisionStageInputV1(
                    "decision-stage-input/v1",
                    "trace-1",
                    "trace-1",
                    "tick-1",
                    DecisionStageName.PAIR_BUNDLE,
                    Map.of("decisionTime", Instant.parse("2026-04-23T00:00:00Z")),
                    Map.of("window", List.of(Map.ofEntries(
                            Map.entry("id", "bundle-1"),
                            Map.entry("bundleId", "bundle-1"),
                            Map.entry("pickupLat", 10.0),
                            Map.entry("pickupLng", 106.0),
                            Map.entry("dropLat", 10.1),
                            Map.entry("dropLng", 106.1),
                            Map.entry("bundleCentroidLat", 10.05),
                            Map.entry("bundleCentroidLng", 106.05),
                            Map.entry("pickupClusterRadiusMeters", 120.0),
                            Map.entry("dropClusterRadiusMeters", 140.0),
                            Map.entry("routeSpreadMeters", 300.0),
                            Map.entry("avgPairSupport", 0.8)))),
                    Map.of(),
                    Map.of(),
                    Map.of(),
                    Map.of(),
                    Map.of(),
                    Map.of(),
                    Map.of(),
                    Map.of(),
                    List.of());

            recorder.recordDecisionStageInput(input);
            writer.flushNow();
        }

        String decisionInputLine = Files.readString(bronzeDir.resolve("decision-stage-input").resolve("trace-1.jsonl"));
        String bundleGeometryLine = Files.readString(bronzeDir.resolve("bundle-geometry-trace").resolve("trace-1.jsonl"));

        assertTrue(decisionInputLine.contains("\"timeLayer\":\"observation\""));
        assertTrue(decisionInputLine.contains("\"antiLeakageClass\":\"DECISION_SAFE\""));
        assertTrue(decisionInputLine.contains("\"candidateId\":\"bundle:bundle-1\""));
        assertTrue(decisionInputLine.contains("\"source\":\"stage-window\""));
        assertTrue(bundleGeometryLine.contains("\"source\":\"bundle-geometry\""));
    }
}
