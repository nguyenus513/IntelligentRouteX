package com.routechain.v2.harvest;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertTrue;

class HarvestRailWriterTest {

    @Test
    void writesAppendOnlyRowsIntoBronzeFamilyDirectories() throws Exception {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        Path bronzeDir = Files.createTempDirectory("dispatch-v2-bronze");
        properties.getHarvest().setBaseDir(bronzeDir.toString());
        try (HarvestRailWriter writer = new HarvestRailWriter(properties)) {
            writer.write(HarvestFamily.DECISION_STAGE_INPUT, "trace-1", Map.of("traceId", "trace-1", "rowType", "candidate", "candidateId", "bundle:bundle-1"));
            writer.flushNow();
        }
        assertTrue(Files.isRegularFile(bronzeDir.resolve("decision-stage-input").resolve("trace-1.jsonl")));
    }
}
