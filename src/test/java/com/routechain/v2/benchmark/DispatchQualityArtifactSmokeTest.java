package com.routechain.v2.benchmark;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.routechain.v2.perf.DispatchPerfBenchmarkHarness;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchQualityArtifactSmokeTest {
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper().findAndRegisterModules();
    private final DispatchQualityBenchmarkHarness harness = new DispatchQualityBenchmarkHarness();

    @TempDir
    Path tempDir;

    @Test
    void writesQualityBenchmarkArtifactsForRequestedCell() throws Exception {
        String baselinesWire = value("dispatchQuality.baselines", "DISPATCH_QUALITY_BASELINES", "A,B,C");
        String sizeWire = value("dispatchQuality.size", "DISPATCH_QUALITY_SIZE", "S");
        String scenarioPackWire = value("dispatchQuality.scenarioPack", "DISPATCH_QUALITY_SCENARIO_PACK", "normal-clear");
        String decisionModeWire = value("dispatchQuality.decisionMode", "DISPATCH_QUALITY_DECISION_MODE", "legacy");
        String promptFamilyWire = value("dispatchQuality.promptFamily", "DISPATCH_QUALITY_PROMPT_FAMILY", "v2");
        String executionModeWire = value("dispatchQuality.executionMode", "DISPATCH_QUALITY_EXECUTION_MODE", "CONTROLLED");
        boolean authority = Boolean.parseBoolean(value("dispatchQuality.authority", "DISPATCH_QUALITY_AUTHORITY", "false"));
        String outputDirWire = value("dispatchQuality.outputDir", "DISPATCH_QUALITY_OUTPUT_DIR", "build/dispatch-quality-smoke");
        System.out.printf(
                "[CELL STARTED] baselines=%s size=%s scenario-pack=%s decision-mode=%s prompt-family=%s execution-mode=%s authority=%s%n",
                baselinesWire,
                sizeWire,
                scenarioPackWire,
                decisionModeWire,
                promptFamilyWire,
                executionModeWire,
                authority);
        List<DispatchPerfBenchmarkHarness.BaselineId> baselines = parseBaselines(value("dispatchQuality.baselines", "DISPATCH_QUALITY_BASELINES", "A,B,C"));
        DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                baselines,
                DispatchPerfBenchmarkHarness.WorkloadSize.valueOf(sizeWire),
                DispatchQualityBenchmarkHarness.ScenarioPack.fromWire(scenarioPackWire),
                DispatchBenchmarkDecisionMode.fromWire(decisionModeWire),
                promptFamilyWire,
                DispatchQualityBenchmarkHarness.ExecutionMode.valueOf(executionModeWire.toUpperCase().replace('-', '_')),
                value("dispatchQuality.machineLabel", "DISPATCH_QUALITY_MACHINE_LABEL", DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL),
                authority,
                Boolean.parseBoolean(value("dispatchQuality.runDeferredXl", "DISPATCH_QUALITY_RUN_DEFERRED_XL", "false")),
                Path.of(outputDirWire)));
        System.out.printf("[CELL ATTACH SNAPSHOT CAPTURED] worker-snapshots=%d%n",
                run.rawResults().stream()
                        .mapToInt(result -> result.workerStatusSnapshot().size())
                        .sum());
        System.out.printf("[CELL DISPATCH COMPLETED] raw-results=%d comparison=%s%n",
                run.rawResults().size(),
                run.comparisonReport() != null);

        DispatchQualityArtifactWriter.BenchmarkArtifacts artifacts = DispatchQualityArtifactWriter.writeBenchmarkRun(
                run,
                Path.of(outputDirWire));
        System.out.printf("[CELL ARTIFACT WRITTEN] raw-json=%d raw-md=%d comparison-json=%s%n",
                artifacts.rawJsonPaths().size(),
                artifacts.rawMarkdownPaths().size(),
                artifacts.comparisonJsonPath() != null);

        assertFalse(artifacts.rawJsonPaths().isEmpty());
        assertTrue(artifacts.rawJsonPaths().stream().allMatch(path -> path.toFile().isFile()));
        DispatchQualityBenchmarkResult firstResult = OBJECT_MAPPER.readValue(
                Files.readString(artifacts.rawJsonPaths().getFirst()),
                DispatchQualityBenchmarkResult.class);
        assertNotNull(firstResult.executionPolicy());
        assertNotNull(firstResult.artifactWriteCompletedAt());
        assertNotNull(firstResult.timeoutPhase());
        assertTrue(promptFamilyWire.equals(firstResult.promptFamily()));
        if (run.comparisonReport() != null) {
            assertNotNull(artifacts.comparisonJsonPath());
            assertTrue(artifacts.comparisonJsonPath().toFile().isFile());
            assertTrue(artifacts.comparisonCsvPath().toFile().isFile());
        }
    }

    @Test
    void repeatedBenchmarkWritesProduceDistinctRawJsonArtifacts() throws Exception {
        Path outputDir = Path.of(tempDir.toString(), "repeat-artifacts");
        DispatchQualityBenchmarkRun firstRun = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                List.of(DispatchPerfBenchmarkHarness.BaselineId.C),
                DispatchPerfBenchmarkHarness.WorkloadSize.S,
                DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                DispatchBenchmarkDecisionMode.LEGACY,
                "v2",
                DispatchQualityBenchmarkHarness.ExecutionMode.CONTROLLED,
                DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                false,
                false,
                outputDir));
        Thread.sleep(5L);
        DispatchQualityBenchmarkRun secondRun = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                List.of(DispatchPerfBenchmarkHarness.BaselineId.C),
                DispatchPerfBenchmarkHarness.WorkloadSize.S,
                DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                DispatchBenchmarkDecisionMode.LEGACY,
                "v2",
                DispatchQualityBenchmarkHarness.ExecutionMode.CONTROLLED,
                DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                false,
                false,
                outputDir));

        DispatchQualityArtifactWriter.BenchmarkArtifacts firstArtifacts = DispatchQualityArtifactWriter.writeBenchmarkRun(firstRun, outputDir);
        DispatchQualityArtifactWriter.BenchmarkArtifacts secondArtifacts = DispatchQualityArtifactWriter.writeBenchmarkRun(secondRun, outputDir);

        Set<Path> rawJsonPaths = new HashSet<>();
        rawJsonPaths.addAll(firstArtifacts.rawJsonPaths());
        rawJsonPaths.addAll(secondArtifacts.rawJsonPaths());
        assertTrue(rawJsonPaths.size() >= 2);
        try (var paths = Files.list(outputDir)) {
            assertTrue(paths.filter(path -> path.getFileName().toString().endsWith(".json")).count() >= 2);
        }
    }

    private List<DispatchPerfBenchmarkHarness.BaselineId> parseBaselines(String value) {
        return java.util.Arrays.stream(value.split(","))
                .map(String::trim)
                .filter(token -> !token.isBlank())
                .map(DispatchPerfBenchmarkHarness.BaselineId::valueOf)
                .toList();
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
}
