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
        String promptFamily,
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
        DispatchQualityExecutionPolicy executionPolicy,
        String osProfile,
        Instant cellStartedAt,
        Instant dispatchCompletedAt,
        Instant cellCompletedAt,
        Instant artifactWriteCompletedAt,
        DispatchQualityTimeoutPhase timeoutPhase,
        List<DispatchStagePromotionBlocker> promotionBlockers,
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
        promotionBlockers = promotionBlockers == null ? List.of() : List.copyOf(promotionBlockers);
        timeoutPhase = timeoutPhase == null ? DispatchQualityTimeoutPhase.NONE : timeoutPhase;
    }

    public DispatchQualityBenchmarkResult withArtifactWriteCompletedAt(Instant artifactWriteCompletedAt) {
        return new DispatchQualityBenchmarkResult(
                schemaVersion,
                benchmarkTimestamp,
                gitCommit,
                machineProfile,
                decisionMode,
                promptFamily,
                runtimeClassification,
                authoritativeStages,
                executionMode,
                runAuthorityClass,
                authoritative,
                authorityEligible,
                sampleCountOverrideApplied,
                resolvedModelManifestPath,
                manifestExists,
                workerBaseUrls,
                activeMlFlags,
                workerStatusSnapshot,
                mlAttachStatus,
                mlAttachmentFailureReasons,
                baselineId,
                scenarioPack,
                scenarioName,
                workloadSize,
                traceFamilyId,
                decisionStages,
                executionPolicy,
                osProfile,
                cellStartedAt,
                dispatchCompletedAt,
                cellCompletedAt,
                artifactWriteCompletedAt,
                timeoutPhase,
                promotionBlockers,
                deferred,
                metrics,
                intelligenceMetrics,
                llmShadowAgreement,
                routeVectorMetrics,
                tokenUsageSummary,
                stageFallbackSummary,
                degradeReasons,
                workerAppliedSources,
                liveAppliedSources,
                notes);
    }
}
