package com.routechain.v2.harvest;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HarvestRailWriterTest {

    @Test
    void writesAppendOnlyRowsIntoBronzeFamilyDirectories() throws Exception {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        Path bronzeDir = Files.createTempDirectory("dispatch-v2-bronze");
        properties.getHarvest().setBaseDir(bronzeDir.toString());
        try (HarvestRailWriter writer = new HarvestRailWriter(properties)) {
            writer.write(HarvestFamily.DECISION_STAGE_INPUT, "trace-1", Map.ofEntries(
                    Map.entry("schemaVersion", "bronze-candidate-row/v1"),
                    Map.entry("rowType", "candidate"),
                    Map.entry("timeLayer", "observation"),
                    Map.entry("antiLeakageClass", "DECISION_SAFE"),
                    Map.entry("traceId", "trace-1"),
                    Map.entry("runId", "trace-1"),
                    Map.entry("tickId", "tick-1"),
                    Map.entry("stageName", "pair-bundle"),
                    Map.entry("entityType", "bundle"),
                    Map.entry("entityId", "bundle-1"),
                    Map.entry("candidateId", "bundle:bundle-1")));
            writer.flushNow();
        }
        Path target = bronzeDir.resolve("decision-stage-input").resolve("trace-1.jsonl");
        assertTrue(Files.isRegularFile(target));
        List<String> lines = Files.readAllLines(target);
        assertEquals(1, lines.size());
        assertTrue(lines.get(0).contains("\"timeLayer\":\"observation\""));
        assertTrue(lines.get(0).contains("\"antiLeakageClass\":\"DECISION_SAFE\""));
    }
}
