package com.routechain.v2.benchmark;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class DispatchQualityArtifactWriter {
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper().findAndRegisterModules();
    private static final DateTimeFormatter FILE_TS = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS")
            .withZone(ZoneOffset.UTC);

    private DispatchQualityArtifactWriter() {
    }

    public static BenchmarkArtifacts writeBenchmarkRun(DispatchQualityBenchmarkRun run, Path outputDirectory) throws IOException {
        Files.createDirectories(outputDirectory);
        List<Path> rawJsonPaths = new ArrayList<>();
        List<Path> rawMarkdownPaths = new ArrayList<>();
        for (DispatchQualityBenchmarkResult result : run.rawResults()) {
            DispatchQualityBenchmarkResult writtenResult = result.withArtifactWriteCompletedAt(java.time.Instant.now());
            String stem = benchmarkStem(writtenResult);
            Path jsonPath = outputDirectory.resolve(stem + ".json");
            Path markdownPath = outputDirectory.resolve(stem + ".md");
            OBJECT_MAPPER.writerWithDefaultPrettyPrinter().writeValue(jsonPath.toFile(), writtenResult);
            Files.writeString(markdownPath, markdownForBenchmarkResult(writtenResult));
            rawJsonPaths.add(jsonPath);
            rawMarkdownPaths.add(markdownPath);
        }

        Path comparisonJsonPath = null;
        Path comparisonMarkdownPath = null;
        Path comparisonCsvPath = null;
        if (run.comparisonReport() != null) {
            String stem = comparisonStem(run.comparisonReport());
            comparisonJsonPath = outputDirectory.resolve(stem + ".json");
            comparisonMarkdownPath = outputDirectory.resolve(stem + ".md");
            comparisonCsvPath = outputDirectory.resolve(stem + ".csv");
            OBJECT_MAPPER.writerWithDefaultPrettyPrinter().writeValue(comparisonJsonPath.toFile(), run.comparisonReport());
            Files.writeString(comparisonMarkdownPath, markdownForComparison(run.comparisonReport()));
            Files.writeString(comparisonCsvPath, csvForComparison(run.comparisonReport()));
        }

        return new BenchmarkArtifacts(
                List.copyOf(rawJsonPaths),
                List.copyOf(rawMarkdownPaths),
                comparisonJsonPath,
                comparisonMarkdownPath,
                comparisonCsvPath);
    }

    public static AblationArtifacts writeAblationResult(DispatchAblationResult result, Path outputDirectory) throws IOException {
        Files.createDirectories(outputDirectory);
        String stem = ablationStem(result);
        Path jsonPath = outputDirectory.resolve(stem + ".json");
        Path markdownPath = outputDirectory.resolve(stem + ".md");
        Path csvPath = outputDirectory.resolve(stem + ".csv");
        OBJECT_MAPPER.writerWithDefaultPrettyPrinter().writeValue(jsonPath.toFile(), result);
        Files.writeString(markdownPath, markdownForAblation(result));
        Files.writeString(csvPath, csvForAblation(result));
        return new AblationArtifacts(jsonPath, markdownPath, csvPath);
    }

    public static List<Path> jsonArtifacts(Path outputDirectory) throws IOException {
        if (!Files.exists(outputDirectory)) {
            return List.of();
        }
        try (var stream = Files.list(outputDirectory)) {
            return stream
                    .filter(path -> path.getFileName().toString().endsWith(".json"))
                    .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                    .toList();
        }
    }

    public static DispatchQualityComparisonReport readComparisonReport(Path path) throws IOException {
        return OBJECT_MAPPER.readValue(path.toFile(), DispatchQualityComparisonReport.class);
    }

    private static String markdownForBenchmarkResult(DispatchQualityBenchmarkResult result) {
        DispatchQualityMetrics metrics = result.metrics();
        StringBuilder builder = new StringBuilder("# Dispatch Quality Benchmark\n\n");
        builder.append("- baseline: `").append(result.baselineId()).append("`\n");
        builder.append("- scenario: `").append(result.scenarioPack()).append(" / ").append(result.scenarioName()).append("`\n");
        builder.append("- workload: `").append(result.workloadSize()).append("`\n");
        builder.append("- decision mode: `").append(result.decisionMode()).append("`\n");
        builder.append("- prompt family: `").append(result.promptFamily()).append("`\n");
        builder.append("- runtime classification: `").append(result.runtimeClassification()).append("`\n");
        builder.append("- authoritative stages: `").append(result.authoritativeStages()).append("`\n");
        builder.append("- execution mode: `").append(result.executionMode()).append("`\n");
        builder.append("- execution policy: `").append(result.executionPolicy() == null ? "" : result.executionPolicy().policyName()).append("`\n");
        builder.append("- os profile: `").append(result.osProfile()).append("`\n");
        builder.append("- authority class: `").append(result.runAuthorityClass()).append("`\n");
        builder.append("- authority eligible: `").append(result.authorityEligible()).append("`\n");
        builder.append("- timeout phase: `").append(result.timeoutPhase().wireName()).append("`\n");
        builder.append("- cell started at: `").append(result.cellStartedAt()).append("`\n");
        builder.append("- dispatch completed at: `").append(result.dispatchCompletedAt()).append("`\n");
        builder.append("- cell completed at: `").append(result.cellCompletedAt()).append("`\n");
        builder.append("- artifact write completed at: `").append(result.artifactWriteCompletedAt()).append("`\n");
        builder.append("- model manifest: `").append(result.resolvedModelManifestPath()).append("`\n");
        builder.append("- manifest exists: `").append(result.manifestExists()).append("`\n");
        builder.append("- ml attach status: `").append(result.mlAttachStatus()).append("`\n");
        builder.append("- decision exact-match rate: `").append(result.decisionAgreement().overallExactMatchRate()).append("`\n");
        builder.append("- token requests: `").append(result.tokenUsageSummary().requestCount()).append("`\n");
        builder.append("- token total: `").append(result.tokenUsageSummary().totalTokens()).append("`\n");
        builder.append("- stage fallbacks: `").append(result.stageFallbackSummary().totalFallbacks()).append("`\n");
        DispatchBundleDiversityMetrics bundleDiversity = result.bundleDiversity();
        builder.append("\n## Bundle Diversity\n\n");
        builder.append("- candidates retained: `").append(bundleDiversity.candidateCount())
                .append(" -> ").append(bundleDiversity.retainedCount()).append("`\n");
        builder.append("- family diversity count: `").append(bundleDiversity.familyDiversityCount()).append("`\n");
        builder.append("- diversity retained count: `").append(bundleDiversity.diversityRetainedCount()).append("`\n");
        builder.append("- late-risk rescue candidates: `").append(bundleDiversity.lateRiskRescueCandidateCount()).append("`\n");
        builder.append("- active-route addon candidates: `").append(bundleDiversity.activeRouteAddonCandidateCount()).append("`\n");
        builder.append("- family generated counts: `").append(bundleDiversity.familyGeneratedCounts()).append("`\n");
        builder.append("- family retained counts: `").append(bundleDiversity.familyRetainedCounts()).append("`\n");
        builder.append("- rejected reasons: `").append(bundleDiversity.rejectedByReasonCounts()).append("`\n");
        DispatchSelectorTelemetryMetrics selectorTelemetry = result.selectorTelemetry();
        builder.append("\n## Selector Telemetry\n\n");
        builder.append("- selector mode: `").append(selectorTelemetry.mode()).append("`\n");
        builder.append("- pool input/reduced/rejected: `")
                .append(selectorTelemetry.poolInputCount()).append(" / ")
                .append(selectorTelemetry.poolReducedCount()).append(" / ")
                .append(selectorTelemetry.poolRejectedCount()).append("`\n");
        builder.append("- timed out: `").append(selectorTelemetry.timedOut()).append("`\n");
        builder.append("- fallback level: `").append(selectorTelemetry.fallbackLevel()).append("`\n");
        builder.append("- max pool size: `").append(selectorTelemetry.selectorMaxPoolSize()).append("`\n");
        builder.append("- pool cap applied: `").append(selectorTelemetry.selectorPoolCapApplied()).append("`\n");
        builder.append("- pool cap objective loss: `").append(selectorTelemetry.selectorPoolCapObjectiveLoss()).append("`\n");
        builder.append("- acceptance gate passed: `").append(selectorTelemetry.acceptanceGatePassed()).append("`\n");
        builder.append("- acceptance rejected reasons: `").append(selectorTelemetry.acceptanceGateRejectedReasons()).append("`\n");
        DispatchObjectiveTelemetryMetrics objectiveTelemetry = result.objectiveTelemetry();
        builder.append("\n## Objective Telemetry\n\n");
        builder.append("- breakdown count: `").append(objectiveTelemetry.breakdownCount()).append("`\n");
        builder.append("- selected total utility: `").append(objectiveTelemetry.selectedTotalUtility()).append("`\n");
        builder.append("- selected quality cost: `").append(objectiveTelemetry.selectedQualityCost()).append("`\n");
        builder.append("- selected risk cost: `").append(objectiveTelemetry.selectedRiskCost()).append("`\n");
        builder.append("- selected runtime cost: `").append(objectiveTelemetry.selectedRuntimeCost()).append("`\n");
        builder.append("- selected reward: `").append(objectiveTelemetry.selectedReward()).append("`\n");
        builder.append("- selected top reasons: `").append(objectiveTelemetry.selectedTopReasons()).append("`\n");
        DispatchRepairTelemetryMetrics repair = result.activeRepair();
        builder.append("\n## Active Repair\n\n");
        builder.append("- mode: `").append(repair.mode()).append("`\n");
        builder.append("- enabled: `").append(repair.enabled()).append("`\n");
        builder.append("- timed out: `").append(repair.timedOut()).append("`\n");
        builder.append("- runtime ms: `").append(repair.runtimeMs()).append("`\n");
        builder.append("- candidate input/output: `").append(repair.candidateInputCount()).append(" / ").append(repair.candidateOutputCount()).append("`\n");
        builder.append("- operators tried: `").append(repair.operatorsTried()).append("`\n");
        builder.append("- accepted/rejected moves: `").append(repair.acceptedMoves()).append(" / ").append(repair.rejectedMoves()).append("`\n");
        builder.append("- best improvement delta: `").append(repair.bestImprovementDelta()).append("`\n");
        builder.append("- frozen prefix violations: `").append(repair.frozenPrefixViolationCount()).append("`\n");
        builder.append("- food duration violations: `").append(repair.foodDurationViolationCount()).append("`\n");
        builder.append("- freshness improvement delta: `").append(repair.freshnessImprovementDelta()).append("`\n");
        builder.append("- tail-risk improvement delta: `").append(repair.tailRiskImprovementDelta()).append("`\n");
        builder.append("- operator counts: `").append(repair.operatorCounts()).append("`\n");
        builder.append("- rejection reasons: `").append(repair.rejectionReasons()).append("`\n");
        builder.append("- degrade reasons: `").append(repair.degradeReasons()).append("`\n");
        builder.append("\n## Route Evidence\n\n");
        builder.append("- route vector geometry coverage: `").append(result.routeVectorMetrics().geometryCoverage()).append("`\n");
        builder.append("- route proposal budget mode: `").append(result.routeProposalBudgetMetrics().budgetMode()).append("`\n");
        builder.append("- route proposals before/after prune: `")
                .append(result.routeProposalBudgetMetrics().candidateCountBeforePrune())
                .append(" -> ")
                .append(result.routeProposalBudgetMetrics().candidateCountAfterPrune())
                .append("`\n");
        builder.append("- route vector cache hit rate: `").append(result.routeProposalBudgetMetrics().routeVectorCacheHitRate()).append("`\n");
        builder.append("- selected proposals: `").append(metrics.selectedProposalCount()).append("`\n");
        builder.append("- executed assignments: `").append(metrics.executedAssignmentCount()).append("`\n");
        builder.append("- conflict free: `").append(metrics.conflictFreeAssignments()).append("`\n");
        builder.append("- execution valid: `").append(metrics.executionValid()).append("`\n");
        builder.append("- bundle rate: `").append(metrics.bundleRate()).append("`\n");
        builder.append("- selected bundle sizes: `1=").append(metrics.selectedSingleOrderCount())
                .append(", 2=").append(metrics.selectedBundleSize2Count())
                .append(", 3=").append(metrics.selectedBundleSize3Count())
                .append(", 4=").append(metrics.selectedBundleSize4Count())
                .append(", 5=").append(metrics.selectedBundleSize5Count())
                .append("`\n");
        builder.append("- covered orders: `").append(metrics.coveredOrderCount()).append("`\n");
        builder.append("- max selected bundle size: `").append(metrics.maxSelectedBundleSize()).append("`\n");
        builder.append("- robust utility avg: `").append(metrics.robustUtilityAverage()).append("`\n");
        builder.append("- route cost quality: `").append(metrics.routeCostQuality()).append("`\n");
        builder.append("- driver entry quality: `").append(metrics.driverEntryQuality()).append("`\n");
        builder.append("- burst robustness: `").append(metrics.burstRobustness()).append("`\n");
        builder.append("- dispatch regret avg: `").append(metrics.dispatchRegretAverage()).append("`\n");
        builder.append("- context efficiency: `").append(result.intelligenceMetrics().contextEfficiency()).append("`\n");
        builder.append("- selector objective: `").append(metrics.selectorObjectiveValue()).append("`\n");
        if (!result.workerBaseUrls().isEmpty()) {
            builder.append("- worker base urls: `").append(result.workerBaseUrls()).append("`\n");
        }
        if (!result.activeMlFlags().isEmpty()) {
            builder.append("- active ml flags: `").append(result.activeMlFlags()).append("`\n");
        }
        if (!result.mlAttachmentFailureReasons().isEmpty()) {
            builder.append("- ml attachment failure reasons: `").append(result.mlAttachmentFailureReasons()).append("`\n");
        }
        if (!result.workerStatusSnapshot().isEmpty()) {
            builder.append("\n## Worker Attachment Snapshot\n\n");
            for (DispatchQualityWorkerStatus worker : result.workerStatusSnapshot()) {
                builder.append("- `").append(worker.workerName()).append("` ")
                        .append("enabled=`").append(worker.enabled()).append("` ")
                        .append("ready=`").append(worker.ready()).append("` ")
                        .append("reachable=`").append(worker.reachable()).append("` ")
                        .append("applied=`").append(worker.applied()).append("` ")
                        .append("workerAuditPresent=`").append(worker.workerAuditPresent()).append("` ")
                        .append("workerAuditSource=`").append(worker.workerAuditSource()).append("` ")
                        .append("workerAuditMissingFields=`").append(worker.workerAuditMissingFields()).append("` ")
                        .append("reason=`").append(worker.readyReason()).append("` ")
                        .append("notAppliedReason=`").append(worker.notAppliedReason()).append("` ")
                        .append("baseUrl=`").append(worker.baseUrl()).append("`")
                        .append('\n');
            }
        }
        if (!result.decisionAgreement().stageAgreements().isEmpty()) {
            builder.append("\n## LLM Agreement\n\n");
            for (DispatchDecisionStageAgreement stageAgreement : result.decisionAgreement().stageAgreements()) {
                builder.append("- `").append(stageAgreement.stageName()).append("` ")
                        .append("rate=`").append(stageAgreement.exactMatchRate()).append("` ")
                        .append("matches=`").append(stageAgreement.exactMatchCount()).append('/')
                        .append(stageAgreement.comparisonCount()).append("`\n");
            }
        }
        if (result.stageFallbackSummary().totalFallbacks() > 0) {
            builder.append("\n## Stage Fallbacks\n\n");
            result.stageFallbackSummary().fallbackCountsByStage().forEach((stage, count) ->
                    builder.append("- `").append(stage).append("` count=`").append(count)
                            .append("` reason=`")
                            .append(result.stageFallbackSummary().latestFallbackReasonByStage().getOrDefault(stage, ""))
                            .append("`\n"));
        }
        if (!result.promotionBlockers().isEmpty()) {
            builder.append("\n## Promotion Blockers\n\n");
            for (DispatchStagePromotionBlocker blocker : result.promotionBlockers()) {
                builder.append("- `").append(blocker.stageName()).append("` ")
                        .append("ready=`").append(blocker.readyForPromotion()).append("` ")
                        .append("authoritativeCandidate=`").append(blocker.authoritativeCandidate()).append("` ")
                        .append("fallbackCount=`").append(blocker.fallbackCount()).append("` ")
                        .append("providerErrorCount=`").append(blocker.providerErrorCount()).append("` ")
                        .append("routeVectorCoverage=`").append(blocker.routeVectorCoverage()).append("` ")
                        .append("tokenUsagePresent=`").append(blocker.tokenUsagePresent()).append("` ")
                        .append("mlAttachStatus=`").append(blocker.mlAttachStatus()).append("` ")
                        .append("reasons=`").append(blocker.blockerReasons()).append("`")
                        .append('\n');
            }
        }
        if (!result.notes().isEmpty()) {
            builder.append("- notes: `").append(result.notes()).append("`\n");
        }
        return builder.toString();
    }

    private static String markdownForComparison(DispatchQualityComparisonReport report) {
        StringBuilder builder = new StringBuilder("# Dispatch Quality Comparison\n\n");
        builder.append("- scenario: `").append(report.scenarioPack()).append(" / ").append(report.scenarioName()).append("`\n");
        builder.append("- workload: `").append(report.workloadSize()).append("`\n");
        builder.append("- decision mode: `").append(report.decisionMode()).append("`\n");
        builder.append("- authoritative stages: `").append(report.authoritativeStages()).append("`\n");
        builder.append("- execution mode: `").append(report.executionMode()).append("`\n");
        builder.append("- authority class: `").append(report.runAuthorityClass()).append("`\n");
        builder.append("- authority eligible: `").append(report.authorityEligible()).append("`\n");
        builder.append("- summary: ").append(report.comparisonSummary()).append("\n\n");
        builder.append("## Full V2 Advantages\n\n");
        if (report.fullV2Advantages().isEmpty()) {
            builder.append("- none\n");
        } else {
            for (String advantage : report.fullV2Advantages()) {
                builder.append("- ").append(advantage).append('\n');
            }
        }
        builder.append("\n## Full V2 Regressions\n\n");
        if (report.fullV2Regressions().isEmpty()) {
            builder.append("- none\n");
        } else {
            for (String regression : report.fullV2Regressions()) {
                builder.append("- ").append(regression).append('\n');
            }
        }
        return builder.toString();
    }

    private static String markdownForAblation(DispatchAblationResult result) {
        StringBuilder builder = new StringBuilder("# Dispatch Quality Ablation\n\n");
        builder.append("- component: `").append(result.toggledComponent()).append("`\n");
        builder.append("- scenario: `").append(result.scenarioPack()).append(" / ").append(result.scenarioName()).append("`\n");
        builder.append("- workload: `").append(result.workloadSize()).append("`\n");
        builder.append("- execution mode: `").append(result.executionMode()).append("`\n");
        builder.append("\n## Delta Summary\n\n");
        for (String line : result.deltaSummary()) {
            builder.append("- ").append(line).append('\n');
        }
        return builder.toString();
    }

    private static String csvForComparison(DispatchQualityComparisonReport report) {
        StringBuilder builder = new StringBuilder();
        builder.append("baseline,scenarioPack,scenarioName,workloadSize,decisionMode,runtimeClassification,executionMode,selectedProposalCount,executedAssignmentCount,conflictFreeAssignments,executionValid,bundleRate,averageBundleSize,selectedSingleOrderCount,selectedBundleSize2Count,selectedBundleSize3Count,selectedBundleSize4Count,selectedBundleSize5Count,coveredOrderCount,maxSelectedBundleSize,routeFallbackRate,averageProjectedPickupEtaMinutes,averageProjectedCompletionEtaMinutes,landingValueAverage,robustUtilityAverage,selectorObjectiveValue,routeCostQuality,driverEntryQuality,burstRobustness,dispatchRegretAverage,courierUtilizationEstimate,degradeRate,workerFallbackRate,liveSourceFallbackRate,decisionExactMatchRate,bundleCandidateCount,bundleRetainedCount,bundleFamilyDiversityCount,bundleDiversityRetainedCount,bundleLateRiskRescueCount,bundleActiveRouteAddonCount,selectorMode,selectorPoolInputCount,selectorPoolReducedCount,selectorPoolRejectedCount,selectorTimedOut,selectorFallbackLevel,selectorMaxPoolSize,selectorPoolCapApplied,selectorPoolCapObjectiveLoss,acceptanceGatePassed,objectiveBreakdownCount,objectiveSelectedTotalUtility,objectiveSelectedQualityCost,objectiveSelectedRiskCost,objectiveSelectedRuntimeCost,objectiveSelectedReward,repairMode,repairEnabled,repairTimedOut,repairRuntimeMs,repairCandidateInputCount,repairCandidateOutputCount,repairOperatorsTried,repairAcceptedMoves,repairRejectedMoves,repairBestImprovementDelta,repairFrozenPrefixViolationCount,repairFoodDurationViolationCount,repairFreshnessImprovementDelta,repairTailRiskImprovementDelta,tokenTotal,stageFallbacks,geometryCoverage,averageRouteDistanceMeters,averageRouteTravelTimeSeconds,averageRouteCost,averageCongestionScore,averageMajorRoadRatio,averageStraightnessScore,averageTurnCount,routeDominanceRate,averageRouteRegret,averagePathEfficiency,averageEtaDominanceScore,contextEfficiency,stageCoherence,fallbackRecoveryQuality,adaptationQuality,decisionConsistencyVariance\n");
        for (DispatchQualityBenchmarkResult result : report.baselineResults()) {
            DispatchQualityMetrics metrics = result.metrics();
            DispatchBundleDiversityMetrics bundleDiversity = result.bundleDiversity();
            DispatchSelectorTelemetryMetrics selectorTelemetry = result.selectorTelemetry();
            DispatchObjectiveTelemetryMetrics objectiveTelemetry = result.objectiveTelemetry();
            builder.append(csv(result.baselineId())).append(',')
                    .append(csv(result.scenarioPack())).append(',')
                    .append(csv(result.scenarioName())).append(',')
                    .append(csv(result.workloadSize())).append(',')
                    .append(csv(result.decisionMode())).append(',')
                    .append(csv(result.runtimeClassification())).append(',')
                    .append(csv(result.executionMode())).append(',')
                    .append(metrics.selectedProposalCount()).append(',')
                    .append(metrics.executedAssignmentCount()).append(',')
                    .append(metrics.conflictFreeAssignments()).append(',')
                    .append(metrics.executionValid()).append(',')
                    .append(metrics.bundleRate()).append(',')
                    .append(metrics.averageBundleSize()).append(',')
                    .append(metrics.selectedSingleOrderCount()).append(',')
                    .append(metrics.selectedBundleSize2Count()).append(',')
                    .append(metrics.selectedBundleSize3Count()).append(',')
                    .append(metrics.selectedBundleSize4Count()).append(',')
                    .append(metrics.selectedBundleSize5Count()).append(',')
                    .append(metrics.coveredOrderCount()).append(',')
                    .append(metrics.maxSelectedBundleSize()).append(',')
                    .append(metrics.routeFallbackRate()).append(',')
                    .append(metrics.averageProjectedPickupEtaMinutes()).append(',')
                    .append(metrics.averageProjectedCompletionEtaMinutes()).append(',')
                    .append(metrics.landingValueAverage()).append(',')
                    .append(metrics.robustUtilityAverage()).append(',')
                    .append(metrics.selectorObjectiveValue()).append(',')
                    .append(metrics.routeCostQuality()).append(',')
                    .append(metrics.driverEntryQuality()).append(',')
                    .append(metrics.burstRobustness()).append(',')
                    .append(metrics.dispatchRegretAverage()).append(',')
                    .append(metrics.courierUtilizationEstimate()).append(',')
                    .append(metrics.degradeRate()).append(',')
                    .append(metrics.workerFallbackRate()).append(',')
                    .append(metrics.liveSourceFallbackRate()).append(',')
                    .append(result.decisionAgreement().overallExactMatchRate()).append(',')
                    .append(bundleDiversity.candidateCount()).append(',')
                    .append(bundleDiversity.retainedCount()).append(',')
                    .append(bundleDiversity.familyDiversityCount()).append(',')
                    .append(bundleDiversity.diversityRetainedCount()).append(',')
                    .append(bundleDiversity.lateRiskRescueCandidateCount()).append(',')
                    .append(bundleDiversity.activeRouteAddonCandidateCount()).append(',')
                    .append(csv(selectorTelemetry.mode())).append(',')
                    .append(selectorTelemetry.poolInputCount()).append(',')
                    .append(selectorTelemetry.poolReducedCount()).append(',')
                    .append(selectorTelemetry.poolRejectedCount()).append(',')
                    .append(selectorTelemetry.timedOut()).append(',')
                    .append(csv(selectorTelemetry.fallbackLevel())).append(',')
                    .append(selectorTelemetry.selectorMaxPoolSize()).append(',')
                    .append(selectorTelemetry.selectorPoolCapApplied()).append(',')
                    .append(selectorTelemetry.selectorPoolCapObjectiveLoss()).append(',')
                    .append(selectorTelemetry.acceptanceGatePassed()).append(',')
                    .append(objectiveTelemetry.breakdownCount()).append(',')
                    .append(objectiveTelemetry.selectedTotalUtility()).append(',')
                    .append(objectiveTelemetry.selectedQualityCost()).append(',')
                    .append(objectiveTelemetry.selectedRiskCost()).append(',')
                    .append(objectiveTelemetry.selectedRuntimeCost()).append(',')
                    .append(objectiveTelemetry.selectedReward()).append(',')
                    .append(csv(result.activeRepair().mode())).append(',')
                    .append(result.activeRepair().enabled()).append(',')
                    .append(result.activeRepair().timedOut()).append(',')
                    .append(result.activeRepair().runtimeMs()).append(',')
                    .append(result.activeRepair().candidateInputCount()).append(',')
                    .append(result.activeRepair().candidateOutputCount()).append(',')
                    .append(result.activeRepair().operatorsTried()).append(',')
                    .append(result.activeRepair().acceptedMoves()).append(',')
                    .append(result.activeRepair().rejectedMoves()).append(',')
                    .append(result.activeRepair().bestImprovementDelta()).append(',')
                    .append(result.activeRepair().frozenPrefixViolationCount()).append(',')
                    .append(result.activeRepair().foodDurationViolationCount()).append(',')
                    .append(result.activeRepair().freshnessImprovementDelta()).append(',')
                    .append(result.activeRepair().tailRiskImprovementDelta()).append(',')
                    .append(result.tokenUsageSummary().totalTokens()).append(',')
                    .append(result.stageFallbackSummary().totalFallbacks()).append(',')
                    .append(result.routeVectorMetrics().geometryCoverage()).append(',')
                    .append(result.routeVectorMetrics().averageTotalDistanceMeters()).append(',')
                    .append(result.routeVectorMetrics().averageTotalTravelTimeSeconds()).append(',')
                    .append(result.routeVectorMetrics().averageRouteCost()).append(',')
                    .append(result.routeVectorMetrics().averageCongestionScore()).append(',')
                    .append(result.routeVectorMetrics().averageMajorRoadRatio()).append(',')
                    .append(result.routeVectorMetrics().averageStraightnessScore()).append(',')
                    .append(result.routeVectorMetrics().averageTurnCount()).append(',')
                    .append(result.routeVectorMetrics().routeDominanceRate()).append(',')
                    .append(result.routeVectorMetrics().averageRouteRegret()).append(',')
                    .append(result.routeVectorMetrics().averagePathEfficiency()).append(',')
                    .append(result.routeVectorMetrics().averageEtaDominanceScore()).append(',')
                    .append(result.intelligenceMetrics().contextEfficiency()).append(',')
                    .append(result.intelligenceMetrics().stageCoherence()).append(',')
                    .append(result.intelligenceMetrics().fallbackRecoveryQuality()).append(',')
                    .append(result.intelligenceMetrics().adaptationQuality()).append(',')
                    .append(result.intelligenceMetrics().decisionConsistencyVariance()).append('\n');
        }
        return builder.toString();
    }

    private static String csvForAblation(DispatchAblationResult result) {
        StringBuilder builder = new StringBuilder();
        builder.append("variant,scenarioPack,scenarioName,workloadSize,executionMode,toggledComponent,selectedProposalCount,executedAssignmentCount,conflictFreeAssignments,bundleRate,averageBundleSize,routeFallbackRate,averageProjectedPickupEtaMinutes,averageProjectedCompletionEtaMinutes,landingValueAverage,robustUtilityAverage,selectorObjectiveValue,routeCostQuality,driverEntryQuality,burstRobustness,degradeRate,workerFallbackRate,liveSourceFallbackRate\n");
        appendMetricsRow(builder, "control", result, result.controlMetrics());
        appendMetricsRow(builder, "variant", result, result.variantMetrics());
        return builder.toString();
    }

    private static void appendMetricsRow(StringBuilder builder,
                                         String variantName,
                                         DispatchAblationResult result,
                                         DispatchQualityMetrics metrics) {
        builder.append(csv(variantName)).append(',')
                .append(csv(result.scenarioPack())).append(',')
                .append(csv(result.scenarioName())).append(',')
                .append(csv(result.workloadSize())).append(',')
                .append(csv(result.executionMode())).append(',')
                .append(csv(result.toggledComponent())).append(',')
                .append(metrics.selectedProposalCount()).append(',')
                .append(metrics.executedAssignmentCount()).append(',')
                .append(metrics.conflictFreeAssignments()).append(',')
                .append(metrics.bundleRate()).append(',')
                .append(metrics.averageBundleSize()).append(',')
                .append(metrics.routeFallbackRate()).append(',')
                .append(metrics.averageProjectedPickupEtaMinutes()).append(',')
                .append(metrics.averageProjectedCompletionEtaMinutes()).append(',')
                .append(metrics.landingValueAverage()).append(',')
                .append(metrics.robustUtilityAverage()).append(',')
                .append(metrics.selectorObjectiveValue()).append(',')
                .append(metrics.routeCostQuality()).append(',')
                .append(metrics.driverEntryQuality()).append(',')
                .append(metrics.burstRobustness()).append(',')
                .append(metrics.degradeRate()).append(',')
                .append(metrics.workerFallbackRate()).append(',')
                .append(metrics.liveSourceFallbackRate()).append('\n');
    }

    private static String benchmarkStem(DispatchQualityBenchmarkResult result) {
        return "dispatch-quality-%s-%s-%s-%s-%s-%s-%s".formatted(
                result.scenarioPack().toLowerCase(),
                result.workloadSize().toLowerCase(),
                result.decisionMode().toLowerCase(),
                result.promptFamily().toLowerCase(),
                result.executionMode().toLowerCase(),
                result.baselineId().toLowerCase(),
                FILE_TS.format(result.benchmarkTimestamp()));
    }

    private static String comparisonStem(DispatchQualityComparisonReport report) {
        return "dispatch-quality-compare-%s-%s-%s-%s-%s".formatted(
                report.scenarioPack().toLowerCase(),
                report.workloadSize().toLowerCase(),
                report.decisionMode().toLowerCase(),
                report.executionMode().toLowerCase(),
                FILE_TS.format(java.time.Instant.now()));
    }

    private static String ablationStem(DispatchAblationResult result) {
        return "dispatch-quality-ablation-%s-%s-%s-%s".formatted(
                result.toggledComponent().toLowerCase().replace('_', '-'),
                result.scenarioPack().toLowerCase(),
                result.workloadSize().toLowerCase(),
                FILE_TS.format(java.time.Instant.now()));
    }

    private static String csv(String value) {
        String escaped = value == null ? "" : value.replace("\"", "\"\"");
        return "\"" + escaped + "\"";
    }

    public record BenchmarkArtifacts(
            List<Path> rawJsonPaths,
            List<Path> rawMarkdownPaths,
            Path comparisonJsonPath,
            Path comparisonMarkdownPath,
            Path comparisonCsvPath) {
    }

    public record AblationArtifacts(
            Path jsonPath,
            Path markdownPath,
            Path csvPath) {
    }
}
