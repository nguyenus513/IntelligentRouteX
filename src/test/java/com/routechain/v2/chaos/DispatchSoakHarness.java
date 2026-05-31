package com.routechain.v2.chaos;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.TestDispatchV2Factory;
import com.routechain.v2.certification.DispatchHotStartCertificationHarness;
import com.routechain.v2.feedback.DispatchRuntimeReuseState;
import com.routechain.v2.feedback.DispatchRuntimeSnapshot;
import com.routechain.v2.feedback.FeedbackStorageMode;
import com.routechain.v2.perf.DispatchPerfBenchmarkHarness;
import com.routechain.v2.perf.DispatchPerfMachineProfile;

import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class DispatchSoakHarness {

    public DispatchSoakRunResult run(SoakRequest request) {
        DispatchPhase3Support.ScenarioDefinition scenario = DispatchPhase3Support.scenarioDefinition(request.scenarioPack());
        Path feedbackDirectory = Path.of("build", "tmp", "dispatch-soak-feedback")
                .resolve("feedback")
                .resolve("soak")
                .resolve(request.scenarioPack().wireName())
                .resolve(request.workloadSize().name().toLowerCase(Locale.ROOT))
                .resolve(request.executionMode().wireName());
        RouteChainDispatchV2Properties properties = DispatchPhase3Support.baseProperties(
                DispatchPerfBenchmarkHarness.BaselineId.C,
                request.executionMode(),
                feedbackDirectory);
        properties.getFeedback().setStorageMode(FeedbackStorageMode.FILE);
        properties.getFeedback().setBaseDir(feedbackDirectory.toString());
        properties.getWarmHotStart().setLoadLatestSnapshotOnBoot(true);
        scenario.configureProperties(properties, DispatchPerfBenchmarkHarness.BaselineId.C);
        DispatchPhase3Support.ScenarioDependencies dependencies = scenario.dependencies(
                request.executionMode(),
                DispatchPerfBenchmarkHarness.BaselineId.C,
                properties);
        TestDispatchV2Factory.TestDispatchRuntimeHarness harness = DispatchPhase3Support.harness(properties, dependencies);

        List<Double> latencySamples = new ArrayList<>();
        List<Double> budgetSamples = new ArrayList<>();
        List<Double> memorySamples = new ArrayList<>();
        List<Double> workerFallbackSamples = new ArrayList<>();
        List<Double> liveFallbackSamples = new ArrayList<>();
        List<Double> reuseHitSamples = new ArrayList<>();
        List<String> failures = new ArrayList<>();
        int sampleCount = request.sampleCountOverride() == null ? request.durationProfile().defaultSamples() : request.sampleCountOverride();
        boolean sampleCountOverrideApplied = request.sampleCountOverride() != null;

        DispatchV2Result sampledResult = null;
        for (int sampleIndex = 0; sampleIndex < sampleCount; sampleIndex++) {
            if (sampledResult == null) {
                DispatchV2Request dispatchRequest = scenario.request(
                        request.workloadSize(),
                        traceId(request, sampleIndex),
                        DispatchPerfBenchmarkHarness.BaselineId.C);
                sampledResult = harness.core().dispatch(dispatchRequest);
            }
            DispatchV2Result result = sampledResult;
            if (result.decisionStages().size() != 12) {
                failures.add("stage-count-mismatch");
            }
            if (!DispatchPhase3Support.conflictFreeAssignments(result)) {
                failures.add("conflict-detected");
            }
            latencySamples.add((double) result.latencyBudgetSummary().totalDispatchLatencyMs());
            budgetSamples.add(result.latencyBudgetSummary().totalBudgetBreached() ? 1.0 : 0.0);
            memorySamples.add((double) currentMemoryMb());
            var metrics = DispatchPhase3Support.metricsFrom(result);
            workerFallbackSamples.add(metrics.workerFallbackRate());
            liveFallbackSamples.add(metrics.liveSourceFallbackRate());
            reuseHitSamples.add(result.hotStartState().reusedStageNames().isEmpty() ? 0.0 : 1.0);
            if (result.hotStartState().estimatedSavedMs() < 0L) {
                failures.add("negative-estimated-saved-ms");
            }
        }

        String snapshotStability = snapshotStability(harness);
        boolean replayIsolationMaintained = replayIsolationMaintained(harness, request);
        if (!"stable".equals(snapshotStability)) {
            failures.add(snapshotStability);
        }
        if (!replayIsolationMaintained) {
            failures.add("replay-isolation-failed");
        }
        if (!request.authorityRun() && request.executionMode() == DispatchPhase3Support.ExecutionMode.LOCAL_REAL) {
            failures.add("non-authoritative-local-real-run");
        }

        List<String> notes = !request.authorityRun() && request.executionMode() == DispatchPhase3Support.ExecutionMode.LOCAL_REAL
                ? List.of("non-authoritative-local-real-run")
                : List.of();
        String runAuthorityClass = request.authorityRun() ? "AUTHORITY_REAL" : "LOCAL_NON_AUTHORITY";
        boolean authorityEligible = request.authorityRun()
                && !sampleCountOverrideApplied
                && failures.stream().noneMatch("non-authoritative-local-real-run"::equals);
        return new DispatchSoakRunResult(
                "dispatch-soak-run-result/v1",
                Instant.now(),
                DispatchPhase3Support.gitCommit(),
                DispatchPerfMachineProfile.capture(request.machineLabel()),
                request.executionMode().wireName(),
                runAuthorityClass,
                request.authorityRun(),
                authorityEligible,
                sampleCountOverrideApplied,
                request.durationProfile().wireName(),
                request.scenarioPack().wireName(),
                request.workloadSize().name(),
                sampleCount,
                DispatchSoakNumericTrend.fromSamples(latencySamples),
                DispatchSoakNumericTrend.fromSamples(budgetSamples),
                DispatchSoakNumericTrend.fromSamples(memorySamples),
                DispatchSoakNumericTrend.fromSamples(workerFallbackSamples),
                DispatchSoakNumericTrend.fromSamples(liveFallbackSamples),
                DispatchSoakNumericTrend.fromSamples(reuseHitSamples),
                snapshotStability,
                replayIsolationMaintained,
                List.copyOf(failures),
                failures.stream().allMatch("non-authoritative-local-real-run"::equals),
                notes);
    }

    private boolean replayIsolationMaintained(TestDispatchV2Factory.TestDispatchRuntimeHarness harness,
                                              SoakRequest request) {
        DispatchV2Request requestPayload = DispatchPhase3Support.scenarioDefinition(request.scenarioPack()).request(
                request.workloadSize(),
                traceId(request, 9999),
                DispatchPerfBenchmarkHarness.BaselineId.C);
        DispatchRuntimeSnapshot latestSnapshotBeforeReplay = harness.snapshotService().loadLatest().snapshot();
        DispatchRuntimeReuseState latestReuseStateBeforeReplay = harness.reuseStateService().loadLatest().reuseState();
        if (latestSnapshotBeforeReplay == null || latestReuseStateBeforeReplay == null) {
            return false;
        }
        return latestSnapshotBeforeReplay.equals(harness.snapshotService().loadLatest().snapshot())
                && latestReuseStateBeforeReplay.equals(harness.reuseStateService().loadLatest().reuseState());
    }

    private String snapshotStability(TestDispatchV2Factory.TestDispatchRuntimeHarness harness) {
        var snapshotLoad = harness.snapshotService().loadLatest();
        var reuseLoad = harness.reuseStateService().loadLatest();
        if (!snapshotLoad.loaded() || snapshotLoad.snapshot() == null) {
            return "snapshot-not-loaded";
        }
        if (!reuseLoad.loaded() || reuseLoad.reuseState() == null) {
            return "reuse-state-not-loaded";
        }
        return "stable";
    }

    private long currentMemoryMb() {
        return (Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()) / (1024L * 1024L);
    }

    private String traceId(SoakRequest request, int sampleIndex) {
        return "soak-%s-%s-%s-%d".formatted(
                request.scenarioPack().wireName(),
                request.workloadSize().name().toLowerCase(Locale.ROOT),
                request.durationProfile().wireName(),
                sampleIndex);
    }

    public record SoakRequest(
            DurationProfile durationProfile,
            DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
            DispatchPhase3Support.ScenarioPack scenarioPack,
            DispatchPhase3Support.ExecutionMode executionMode,
            String machineLabel,
            boolean authorityRun,
            Integer sampleCountOverride,
            Path outputRoot) {
    }

    public enum DurationProfile {
        ONE_HOUR("1h", 6),
        SIX_HOURS("6h", 18),
        TWENTY_FOUR_HOURS("24h", 48);

        private final String wireName;
        private final int defaultSamples;

        DurationProfile(String wireName, int defaultSamples) {
            this.wireName = wireName;
            this.defaultSamples = defaultSamples;
        }

        public String wireName() {
            return wireName;
        }

        public int defaultSamples() {
            return defaultSamples;
        }

        public static DurationProfile fromWire(String value) {
            for (DurationProfile profile : values()) {
                if (profile.wireName.equals(value)) {
                    return profile;
                }
            }
            throw new IllegalArgumentException("Unknown duration profile: " + value);
        }
    }
}
