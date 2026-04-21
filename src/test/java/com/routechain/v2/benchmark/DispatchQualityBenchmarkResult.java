package com.routechain.v2.benchmark;

import com.routechain.v2.SchemaVersioned;
import com.routechain.v2.perf.DispatchPerfMachineProfile;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record DispatchQualityBenchmarkResult(
        String schemaVersion,
        Instant benchmarkTimestamp,
        String gitCommit,
        DispatchPerfMachineProfile machineProfile,
        String decisionMode,
        String runtimeClassification,
        List<String> authoritativeStages,
        String executionMode,
        String runAuthorityClass,
        boolean authoritative,
        boolean authorityEligible,
        boolean sampleCountOverrideApplied,
        String resolvedModelManifestPath,
        boolean manifestExists,
        Map<String, String> workerBaseUrls,
        Map<String, Boolean> activeMlFlags,
        List<DispatchQualityWorkerStatus> workerStatusSnapshot,
        DispatchQualityMlAttachStatus mlAttachStatus,
        List<String> mlAttachmentFailureReasons,
        String baselineId,
        String scenarioPack,
        String scenarioName,
        String workloadSize,
        String traceFamilyId,
        List<String> decisionStages,
        boolean deferred,
        DispatchQualityMetrics metrics,
        DispatchIntelligenceMetrics intelligenceMetrics,
        DispatchLlmShadowAgreementSummary llmShadowAgreement,
        DispatchRouteVectorMetrics routeVectorMetrics,
        DispatchTokenUsageSummary tokenUsageSummary,
        DispatchStageFallbackSummary stageFallbackSummary,
        List<String> degradeReasons,
        List<String> workerAppliedSources,
        List<String> liveAppliedSources,
        List<String> notes) implements SchemaVersioned {

    public DispatchQualityBenchmarkResult {
        authoritativeStages = authoritativeStages == null ? List.of() : List.copyOf(authoritativeStages);
    }
}
