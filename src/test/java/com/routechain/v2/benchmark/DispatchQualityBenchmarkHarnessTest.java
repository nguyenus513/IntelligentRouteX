package com.routechain.v2.benchmark;

import com.routechain.v2.perf.DispatchPerfBenchmarkHarness;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchQualityBenchmarkHarnessTest {
    private final DispatchQualityBenchmarkHarness harness = new DispatchQualityBenchmarkHarness();

    @TempDir
    Path tempDir;

    @Test
    void benchmarkRunEmitsThreeBaselinesAndOneComparisonReport() {
        DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                List.of(
                        DispatchPerfBenchmarkHarness.BaselineId.A,
                        DispatchPerfBenchmarkHarness.BaselineId.B,
                        DispatchPerfBenchmarkHarness.BaselineId.C),
                DispatchPerfBenchmarkHarness.WorkloadSize.S,
                DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                DispatchBenchmarkDecisionMode.LEGACY,
                "v2",
                DispatchQualityBenchmarkHarness.ExecutionMode.CONTROLLED,
                DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                false,
                false,
                tempDir));

        assertEquals(3, run.rawResults().size());
        assertNotNull(run.comparisonReport());
        assertTrue(run.rawResults().stream().allMatch(result -> result.decisionStages().size() == 12));
        assertTrue(run.rawResults().stream().allMatch(result -> !result.deferred()));
        assertTrue(run.rawResults().stream().allMatch(result -> result.decisionMode().equals("legacy")));
        assertTrue(run.rawResults().stream().allMatch(result -> result.promptFamily().equals("v2")));
        assertTrue(run.rawResults().stream().allMatch(result -> result.executionPolicy() != null));
        assertTrue(run.rawResults().stream().allMatch(result -> result.timeoutPhase() == DispatchQualityTimeoutPhase.NONE));
        assertTrue(run.rawResults().stream().allMatch(result -> result.cellStartedAt() != null));
        assertTrue(run.rawResults().stream().allMatch(result -> result.cellCompletedAt() != null));
    }

    @Test
    void stableScenarioKeepsConflictFreeAssignmentsAndPopulatesMetrics() {
        DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                List.of(
                        DispatchPerfBenchmarkHarness.BaselineId.A,
                        DispatchPerfBenchmarkHarness.BaselineId.B,
                        DispatchPerfBenchmarkHarness.BaselineId.C),
                DispatchPerfBenchmarkHarness.WorkloadSize.S,
                DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                DispatchBenchmarkDecisionMode.LEGACY,
                "v2",
                DispatchQualityBenchmarkHarness.ExecutionMode.CONTROLLED,
                DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                false,
                false,
                tempDir));

        DispatchQualityBenchmarkResult fullV2 = run.rawResults().stream()
                .filter(result -> result.baselineId().equals("C"))
                .findFirst()
                .orElseThrow();
        assertTrue(fullV2.metrics().conflictFreeAssignments());
        assertTrue(fullV2.metrics().robustUtilityAverage() >= 0.0);
        assertTrue(fullV2.metrics().selectorObjectiveValue() >= 0.0);
        assertTrue(fullV2.metrics().workerFallbackRate() >= 0.0);
        assertTrue(fullV2.metrics().liveSourceFallbackRate() >= 0.0);
        assertTrue(fullV2.routeVectorMetrics().geometryCoverage() >= 0.0);
        assertEquals(4, fullV2.promotionBlockers().size());
        assertEquals(
                List.of("driver", "route-critique", "scenario", "route-generation"),
                fullV2.promotionBlockers().stream().map(DispatchStagePromotionBlocker::stageName).toList());
    }

    @Test
    void ablationProducesDeltaReportWithoutChangingContracts() {
        DispatchAblationResult result = harness.ablate(new DispatchQualityBenchmarkHarness.AblationRequest(
                DispatchQualityBenchmarkHarness.AblationComponent.ORTOOLS,
                DispatchPerfBenchmarkHarness.WorkloadSize.S,
                DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                DispatchQualityBenchmarkHarness.ExecutionMode.CONTROLLED,
                false,
                tempDir));

        assertEquals("ortools", result.toggledComponent());
        assertFalse(result.deltaSummary().isEmpty());
        assertTrue(result.controlMetrics().conflictFreeAssignments());
        assertTrue(result.variantMetrics().conflictFreeAssignments());
    }

    @Test
    void authorityLocalRealRunCarriesAuthorityClassification() {
        DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                List.of(DispatchPerfBenchmarkHarness.BaselineId.C),
                DispatchPerfBenchmarkHarness.WorkloadSize.S,
                DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                DispatchBenchmarkDecisionMode.LEGACY,
                "v2",
                DispatchQualityBenchmarkHarness.ExecutionMode.LOCAL_REAL,
                DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                true,
                false,
                tempDir));

        DispatchQualityBenchmarkResult result = run.rawResults().getFirst();
        assertEquals("AUTHORITY_REAL", result.runAuthorityClass());
        assertTrue(result.authoritative());
        assertTrue(result.authorityEligible());
        assertFalse(result.notes().contains("non-authoritative-local-real-run"));
    }

    @Test
    void authorityLocalRealRunMarksAttachFailureWhenMlWorkersDoNotApply() {
        Path missingManifest = tempDir.resolve("missing-model-manifest.yaml");
        String previous = System.getProperty("dispatchV2.ml.modelManifestPath");
        System.setProperty("dispatchV2.ml.modelManifestPath", missingManifest.toString());
        try {
        DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                    List.of(DispatchPerfBenchmarkHarness.BaselineId.C),
                    DispatchPerfBenchmarkHarness.WorkloadSize.S,
                    DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                    DispatchBenchmarkDecisionMode.LEGACY,
                    "v2",
                    DispatchQualityBenchmarkHarness.ExecutionMode.LOCAL_REAL,
                    DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                    true,
                    false,
                    tempDir));

            DispatchQualityBenchmarkResult result = run.rawResults().getFirst();
            assertEquals(missingManifest.toAbsolutePath().normalize().toString(), result.resolvedModelManifestPath());
            assertFalse(result.manifestExists());
            assertEquals(DispatchQualityMlAttachStatus.ML_ATTACH_FAIL, result.mlAttachStatus());
            assertTrue(result.mlAttachmentFailureReasons().contains("model-manifest-missing"));
            assertTrue(result.notes().contains("ML_ATTACH_FAIL"));
            assertTrue(result.workerAppliedSources().isEmpty());
            assertFalse(result.workerStatusSnapshot().isEmpty());
        } finally {
            restoreProperty("dispatchV2.ml.modelManifestPath", previous);
        }
    }

    @Test
    void localRealRunWithoutAuthorityFlagRemainsNonAuthoritative() {
        DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                List.of(DispatchPerfBenchmarkHarness.BaselineId.C),
                DispatchPerfBenchmarkHarness.WorkloadSize.S,
                DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                DispatchBenchmarkDecisionMode.LEGACY,
                "v2",
                DispatchQualityBenchmarkHarness.ExecutionMode.LOCAL_REAL,
                DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                false,
                false,
                tempDir));

        DispatchQualityBenchmarkResult result = run.rawResults().getFirst();
        assertEquals("LOCAL_NON_AUTHORITY", result.runAuthorityClass());
        assertFalse(result.authoritative());
        assertFalse(result.authorityEligible());
        assertTrue(result.notes().contains("non-authoritative-local-real-run"));
    }

    @Test
    void localRealRunResolvesManifestPathFromRuntimeStyleOverride() {
        String previous = System.getProperty("dispatchV2.ml.modelManifestPath");
        Path manifest = Path.of("services", "models", "model-manifest.yaml").toAbsolutePath().normalize();
        System.setProperty("dispatchV2.ml.modelManifestPath", manifest.toString());
        try {
        DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                    List.of(DispatchPerfBenchmarkHarness.BaselineId.C),
                    DispatchPerfBenchmarkHarness.WorkloadSize.S,
                    DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                    DispatchBenchmarkDecisionMode.LEGACY,
                    "v2",
                    DispatchQualityBenchmarkHarness.ExecutionMode.LOCAL_REAL,
                    DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                    false,
                    false,
                    tempDir));

            DispatchQualityBenchmarkResult result = run.rawResults().getFirst();
            assertEquals(manifest.toString(), result.resolvedModelManifestPath());
            assertTrue(result.manifestExists());
        } finally {
            restoreProperty("dispatchV2.ml.modelManifestPath", previous);
        }
    }

    @Test
    void llmShadowBenchmarkModePopulatesDecisionFeedbackSummaries() {
        DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                List.of(DispatchPerfBenchmarkHarness.BaselineId.C),
                DispatchPerfBenchmarkHarness.WorkloadSize.S,
                DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                DispatchBenchmarkDecisionMode.LLM_SHADOW,
                "v2",
                DispatchQualityBenchmarkHarness.ExecutionMode.CONTROLLED,
                DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                false,
                false,
                tempDir));

        DispatchQualityBenchmarkResult result = run.rawResults().getFirst();
        assertEquals("llm-shadow", result.decisionMode());
        assertNotNull(result.llmShadowAgreement());
        assertNotNull(result.stageFallbackSummary());
        assertNotNull(result.tokenUsageSummary());
        assertTrue(result.stageFallbackSummary().totalStageOutputs() >= 1);
    }

    @Test
    void fullAdaptiveProfileEmitsAdaptiveComputeTraceArtifacts() {
        String previous = System.getProperty("dispatchQuality.profile");
        System.setProperty("dispatchQuality.profile", "dispatch-v2-full-adaptive");
        try {
            DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                    List.of(DispatchPerfBenchmarkHarness.BaselineId.C),
                    DispatchPerfBenchmarkHarness.WorkloadSize.S,
                    DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                    DispatchBenchmarkDecisionMode.LLM_AUTHORITATIVE,
                    "v2",
                    DispatchQualityBenchmarkHarness.ExecutionMode.CONTROLLED,
                    DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                    false,
                    false,
                    tempDir));

            assertEquals(1, run.rawResults().size());
            DispatchQualityBenchmarkResult result = run.rawResults().getFirst();
            assertTrue(result.workerStatusSnapshot().stream()
                    .filter(DispatchQualityWorkerStatus::enabled)
                    .allMatch(DispatchQualityWorkerStatus::workerAuditPresent));
            Path adaptiveTraceRoot = tempDir
                    .resolve("feedback")
                    .resolve("normal-clear")
                    .resolve("s")
                    .resolve("controlled")
                    .resolve("llm-authoritative")
                    .resolve("v2")
                    .resolve("c")
                    .resolve("decision-stage")
                    .resolve("adaptive_compute_trace");
            assertTrue(java.nio.file.Files.exists(adaptiveTraceRoot));
            try (var traceFiles = java.nio.file.Files.list(adaptiveTraceRoot)) {
                Path tracePath = traceFiles.findFirst().orElseThrow();
                Map<?, ?> payload = new com.fasterxml.jackson.databind.ObjectMapper().readValue(tracePath.toFile(), Map.class);
                assertEquals(Boolean.TRUE, payload.get("workerAuditPresent"));
                assertEquals("ready-state", payload.get("workerAuditSource"));
                assertTrue(((List<?>) payload.get("workerAuditMissingFields")).isEmpty());
            }
        } catch (java.io.IOException exception) {
            throw new RuntimeException(exception);
        } finally {
            restoreProperty("dispatchQuality.profile", previous);
        }
    }

    @Test
    void authorityLocalRealRunUsesWindowsSafeHeavyPolicyOnWindows() {
        String previous = System.getProperty("os.name");
        System.setProperty("os.name", "Windows 11");
        try {
            DispatchQualityBenchmarkRun run = harness.benchmark(new DispatchQualityBenchmarkHarness.BenchmarkRequest(
                    List.of(DispatchPerfBenchmarkHarness.BaselineId.C),
                    DispatchPerfBenchmarkHarness.WorkloadSize.S,
                    DispatchQualityBenchmarkHarness.ScenarioPack.NORMAL_CLEAR,
                    DispatchBenchmarkDecisionMode.LEGACY,
                    "v2",
                    DispatchQualityBenchmarkHarness.ExecutionMode.LOCAL_REAL,
                    DispatchPerfBenchmarkHarness.DEFAULT_MACHINE_LABEL,
                    true,
                    false,
                    tempDir));

            DispatchQualityBenchmarkResult result = run.rawResults().getFirst();
            assertEquals("windows-sequential-heavy", result.executionPolicy().policyName());
            assertTrue(result.executionPolicy().windowsSafeHeavyMode());
            assertTrue(result.executionPolicy().isolatedOutputRoots());
            assertTrue(result.osProfile().startsWith("Windows 11"));
        } finally {
            restoreProperty("os.name", previous);
        }
    }

    @Test
    void timeoutClassificationSeparatesDispatchArtifactAndTaskLockSignals() {
        assertEquals(
                DispatchQualityTimeoutPhase.DISPATCH_TIMEOUT,
                DispatchQualityBenchmarkHarness.classifyTimeoutPhase(new RuntimeException("dispatch stage timed out after 30s")));
        assertEquals(
                DispatchQualityTimeoutPhase.ARTIFACT_WRITE_TIMEOUT,
                DispatchQualityBenchmarkHarness.classifyTimeoutPhase(new RuntimeException("artifact write timed out during markdown flush")));
        assertEquals(
                DispatchQualityTimeoutPhase.TASK_LOCK_TIMEOUT,
                DispatchQualityBenchmarkHarness.classifyTimeoutPhase(new RuntimeException("task lock timed out while waiting for task output")));
    }

    private void restoreProperty(String name, String previous) {
        if (previous == null) {
            System.clearProperty(name);
            return;
        }
        System.setProperty(name, previous);
    }
}
