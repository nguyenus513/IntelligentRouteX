package com.routechain.v2.benchmark;

import com.routechain.v2.perf.DispatchPerfBenchmarkHarness;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchQualityPromptFamilySmokeTest {
    private final DispatchQualityBenchmarkHarness harness = new DispatchQualityBenchmarkHarness();

    @TempDir
    Path tempDir;

    @Test
    void benchmarkResultAndArtifactsCarryPromptFamily() throws Exception {
        DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                List.of(DispatchPerfBenchmarkHarness.BaselineId.A),
                DispatchPerfBenchmarkHarness.WorkloadSize.S,
                DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                DispatchBenchmarkDecisionMode.LEGACY,
                "v3",
                DispatchQualityBenchmarkHarness.ExecutionMode.CONTROLLED,
                DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                false,
                false,
                tempDir));

        DispatchQualityBenchmarkResult result = run.rawResults().getFirst();
        assertEquals("v3", result.promptFamily());

        Path feedbackRoot = tempDir
                .resolve("feedback")
                .resolve("normal-clear")
                .resolve("s")
                .resolve("controlled")
                .resolve("legacy")
                .resolve("v3")
                .resolve("a");
        assertTrue(Files.exists(feedbackRoot));

        DispatchQualityArtifactWriter.BenchmarkArtifacts artifacts = DispatchQualityArtifactWriter.writeBenchmarkRun(run, tempDir);
        assertTrue(artifacts.rawJsonPaths().getFirst().getFileName().toString().contains("-v3-"));
    }
}
