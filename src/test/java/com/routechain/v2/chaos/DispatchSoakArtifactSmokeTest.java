package com.routechain.v2.chaos;

import com.routechain.v2.perf.DispatchPerfBenchmarkHarness;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchSoakArtifactSmokeTest {
    private final DispatchSoakHarness harness = new DispatchSoakHarness();

    @Test
    void writesSoakArtifactsForRequestedCell() throws Exception {
        Path outputDirectory = Path.of(value("dispatchSoak.outputDir", "DISPATCH_SOAK_OUTPUT_DIR", "build/dispatch-soak-smoke"));
        DispatchSoakRunResult result = harness.run(new DispatchSoakHarness.SoakRequest(
                DispatchSoakHarness.DurationProfile.fromWire(value("dispatchSoak.duration", "DISPATCH_SOAK_DURATION", "1h")),
                DispatchPerfBenchmarkHarness.WorkloadSize.valueOf(value("dispatchSoak.size", "DISPATCH_SOAK_SIZE", "S")),
                DispatchPhase3Support.ScenarioPack.fromWire(value("dispatchSoak.scenarioPack", "DISPATCH_SOAK_SCENARIO_PACK", "normal-clear")),
                DispatchPhase3Support.ExecutionMode.fromWire(value("dispatchSoak.executionMode", "DISPATCH_SOAK_EXECUTION_MODE", "controlled")),
                value("dispatchSoak.machineLabel", "DISPATCH_SOAK_MACHINE_LABEL", DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL),
                Boolean.parseBoolean(value("dispatchSoak.authority", "DISPATCH_SOAK_AUTHORITY", "false")),
                optionalIntegerValue("dispatchSoak.sampleCountOverride", "DISPATCH_SOAK_SAMPLE_COUNT_OVERRIDE", 1),
                outputDirectory));

        DispatchStabilityArtifactWriter.ArtifactPaths artifacts = DispatchStabilityArtifactWriter.writeSoakResult(result, outputDirectory);
        assertTrue(artifacts.jsonPath().toFile().isFile());
        assertTrue(artifacts.markdownPath().toFile().isFile());
    }

    private String value(String propertyName, String envName, String defaultValue) {
        String propertyValue = System.getProperty(propertyName);
        if (propertyValue != null && !propertyValue.isBlank()) {
            return propertyValue;
        }
        String envValue = System.getenv(envName);
        if (envValue != null && !envValue.isBlank()) {
            return envValue;
        }
        return defaultValue;
    }

    private Integer optionalIntegerValue(String propertyName, String envName, Integer defaultValue) {
        String propertyValue = System.getProperty(propertyName);
        if (propertyValue != null && !propertyValue.isBlank()) {
            return Integer.parseInt(propertyValue);
        }
        String envValue = System.getenv(envName);
        if (envValue != null && !envValue.isBlank()) {
            return Integer.parseInt(envValue);
        }
        return defaultValue;
    }
}
