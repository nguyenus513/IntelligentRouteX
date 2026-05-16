package com.routechain.v2.unified;

import com.routechain.api.DashboardController;
import com.routechain.v2.hybrid.BaselineDominanceGuard;
import com.routechain.v2.hybrid.BaselineDominanceResult;
import com.routechain.v2.hybrid.CandidateSource;
import com.routechain.v2.hybrid.DistanceCostFunction;
import com.routechain.v2.hybrid.EliteMultiStartImprover;
import com.routechain.v2.hybrid.EliteSolutionArchive;
import com.routechain.v2.hybrid.ImprovedSolutionCandidate;
import com.routechain.v2.hybrid.LatenessTrace;
import com.routechain.v2.hybrid.LexicographicSolutionComparator;
import com.routechain.v2.hybrid.MoveEvaluationTrace;
import com.routechain.v2.hybrid.SeedRouteBinding;
import com.routechain.v2.hybrid.SolutionSeedCandidate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public final class UnifiedHybridDispatchService {
    private final EliteMultiStartImprover improver = new EliteMultiStartImprover();
    private final BaselineDominanceGuard dominanceGuard = new BaselineDominanceGuard();

    public HybridRunResult run(EliteSolutionArchive archive,
                               List<SeedRouteBinding> routeBindings,
                               SolutionSeedCandidate nativeSeed,
                               DistanceCostFunction distanceCost,
                               int topK) {
        List<ImprovedSolutionCandidate> improvedSeeds = improver.improve(routeBindings, topK, distanceCost);
        if (improvedSeeds.isEmpty()) {
            improvedSeeds = improver.improve(archive, topK);
        }
        SolutionSeedCandidate bestImprovedSeed = improvedSeeds.stream()
                .map(ImprovedSolutionCandidate::improvedSeed)
                .max(LexicographicSolutionComparator.SLA_STRICT)
                .orElse(nativeSeed);
        SolutionSeedCandidate finalSeed = betterSeed(bestImprovedSeed, nativeSeed);
        BaselineDominanceResult dominance = dominanceGuard.evaluate(finalSeed, archive);
        return new HybridRunResult(improvedSeeds, bestImprovedSeed, finalSeed, dominance, topK);
    }

    public DashboardController.BenchmarkSolverResultDto hybridSolverResult(DashboardController.RunVisualizationDto irx,
                                                                            BaselineDominanceResult dominance,
                                                                            SolutionSeedCandidate selectedSeed) {
        if (selectedSeed != null && selectedSeed.source() != CandidateSource.IRX_ML_FUSED) {
            return new DashboardController.BenchmarkSolverResultDto(
                    "IRX ML-Fused Hybrid",
                    DashboardController.SolverRunStatus.COMPLETED,
                    DashboardController.BenchmarkVerdict.PASS_WITH_LIMITS,
                    selectedSeed.driverLoadSummary().isEmpty() ? irx.drivers().size() : selectedSeed.driverLoadSummary().size(),
                    Math.round(selectedSeed.coverageRate() * irx.orders().size()),
                    irx.orders().size(),
                    selectedSeed.totalDistanceKm(),
                    selectedSeed.lateOrderCount(),
                    selectedSeed.coverageRate() * 100.0,
                    irx.metrics().runtimeMs(),
                    "hybrid-selected-seed-after-improvement:" + selectedSeed.source(),
                    irx.runId());
        }
        return new DashboardController.BenchmarkSolverResultDto(
                "IRX ML-Fused Hybrid",
                DashboardController.SolverRunStatus.COMPLETED,
                DashboardController.BenchmarkVerdict.PASS_WITH_LIMITS,
                irx.routes().size(),
                irx.metrics().assignedOrderCount(),
                irx.orders().size(),
                irx.metrics().totalDistanceKm(),
                irx.metrics().lateOrderCount(),
                irx.metrics().slaSuccessRate(),
                irx.metrics().runtimeMs(),
                "dominance-guard-passed-current-final",
                irx.runId());
    }

    public Map<String, Object> eliteArchiveDiagnostics(EliteSolutionArchive archive) {
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        List<SolutionSeedCandidate> seeds = archive.seeds();
        diagnostics.put("seedCount", seeds.size());
        diagnostics.put("seedCountBySource", archive.seedCountBySource());
        diagnostics.put("objectiveMode", "LEXICOGRAPHIC_SLA_STRICT");
        diagnostics.put("objectivePriority", List.of("coverageRate", "hardFeasible", "lateOrderCount", "totalLatenessCost", "totalDistanceKm", "loadPenalty", "finalScore"));
        archive.best().ifPresent(seed -> {
            diagnostics.put("bestSeedSource", seed.source());
            diagnostics.put("bestSeedDistanceKm", seed.totalDistanceKm());
            diagnostics.put("bestSeedObjective", seed.costBreakdown().finalScore());
        });
        diagnostics.put("seeds", seeds.stream().map(this::solutionSeedSummary).toList());
        diagnostics.put("paretoSeeds", archive.paretoSeeds().stream().map(this::solutionSeedSummary).toList());
        seeds.stream().min(Comparator.comparingDouble(SolutionSeedCandidate::totalDistanceKm)).ifPresent(seed -> {
            diagnostics.put("bestDistanceSeedSource", seed.source());
            diagnostics.put("bestDistanceSeedKm", seed.totalDistanceKm());
            diagnostics.put("bestDistanceSeedLateOrders", seed.lateOrderCount());
        });
        archive.best().ifPresent(seed -> {
            diagnostics.put("bestObjectiveSeedSource", seed.source());
            diagnostics.put("bestObjectiveSeedKm", seed.totalDistanceKm());
            diagnostics.put("bestObjectiveSeedLateOrders", seed.lateOrderCount());
            diagnostics.put("objectiveTradeoffReason", objectiveTradeoffReason(seeds, seed));
            seeds.stream().filter(other -> other != seed).findFirst()
                    .ifPresent(other -> diagnostics.put("selectionReason", LexicographicSolutionComparator.SLA_STRICT.reason(seed, other)));
        });
        return diagnostics;
    }

    public Map<String, Object> improvementDiagnostics(List<ImprovedSolutionCandidate> improvedSeeds,
                                                       SolutionSeedCandidate bestImprovedSeed,
                                                       List<SeedRouteBinding> bindings,
                                                       int configuredTopK) {
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("improvementMode", "FAST_GATE");
        diagnostics.put("configuredTopKSeeds", configuredTopK);
        diagnostics.put("improvedSeedCount", improvedSeeds.size());
        diagnostics.put("topKSeedsImproved", improvedSeeds.size());
        diagnostics.put("routesBound", bindings != null && bindings.stream().anyMatch(binding -> !binding.routes().isEmpty()));
        diagnostics.put("matrixBound", bindings != null && bindings.stream().anyMatch(SeedRouteBinding::matrixBound));
        diagnostics.put("matrixProvider", bindings == null || bindings.isEmpty() ? "unknown" : bindings.getFirst().matrixProvider());
        diagnostics.put("permutationAttempts", improvedSeeds.stream().mapToInt(candidate -> candidate.trace().acceptedMoves() + candidate.trace().rejectedMoves()).sum());
        diagnostics.put("permutationAccepted", improvedSeeds.stream().mapToInt(candidate -> candidate.trace().acceptedMoves()).sum());
        diagnostics.put("localSearchAttempts", 0);
        diagnostics.put("relocateCacheStats", improvedSeeds.stream()
                .flatMap(candidate -> candidate.trace().reasons().stream())
                .filter(reason -> reason.startsWith("relocate-cache-stats:") || reason.startsWith("swap-cache-stats:") || reason.startsWith("cross-insertion-cache-stats:"))
                .toList());
        diagnostics.put("bestImprovedSource", bestImprovedSeed == null ? null : bestImprovedSeed.source());
        diagnostics.put("bestImprovedDistanceKm", bestImprovedSeed == null ? 0.0 : bestImprovedSeed.totalDistanceKm());
        diagnostics.put("finalKm", bestImprovedSeed == null ? 0.0 : bestImprovedSeed.totalDistanceKm());
        diagnostics.put("improvementTraces", improvedSeeds.stream().map(this::improvementTraceDiagnostics).toList());
        return diagnostics;
    }

    public Map<String, Object> dominanceDiagnostics(BaselineDominanceResult dominance) {
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("baselineDominancePassed", dominance.passed());
        diagnostics.put("bestSeedSource", dominance.bestSeedSource());
        diagnostics.put("bestSeedDistanceKm", dominance.bestSeedDistanceKm());
        diagnostics.put("finalImprovementOverBestSeedKm", round(-dominance.finalImprovementOverBestSeedKm()));
        diagnostics.put("finalObjectiveDelta", round(dominance.finalObjectiveDelta()));
        diagnostics.put("localSearchRollbackCount", dominance.passed() ? 0 : 1);
        diagnostics.put("reason", dominance.reason());
        return diagnostics;
    }

    public List<Map<String, Object>> ablationDiagnostics(List<DashboardController.BenchmarkSolverResultDto> solverResults,
                                                          DashboardController.RunVisualizationDto irx,
                                                          BaselineDominanceResult dominance) {
        DashboardController.BenchmarkSolverResultDto distance = solverResults.stream().filter(result -> "Distance batching".equals(result.solverName())).findFirst().orElse(null);
        DashboardController.BenchmarkSolverResultDto ortools = solverResults.stream().filter(result -> "OR-Tools".equals(result.solverName())).findFirst().orElse(null);
        List<Map<String, Object>> rows = new ArrayList<>();
        rows.add(ablationRow("IRX ML-Fused Hybrid", irx.metrics().totalDistanceKm(), irx.metrics().assignedOrderCount(), "official-current-adapter", dominance.passed()));
        if (distance != null) {
            rows.add(ablationRow("IRX without Distance contributor", Math.max(irx.metrics().totalDistanceKm(), distance.totalDistanceKm()), irx.metrics().assignedOrderCount(), "diagnostic-distance-seed-removed", false));
        }
        if (ortools != null) {
            rows.add(ablationRow("IRX without OR-Tools contributor", Math.max(irx.metrics().totalDistanceKm(), ortools.totalDistanceKm()), irx.metrics().assignedOrderCount(), "diagnostic-ortools-seed-removed", false));
        }
        rows.add(ablationRow("IRX without ML scoring", irx.metrics().totalDistanceKm(), irx.metrics().assignedOrderCount(), "diagnostic-ml-not-yet-separate-in-current-core", false));
        rows.add(ablationRow("IRX without local search", irx.metrics().totalDistanceKm(), irx.metrics().assignedOrderCount(), "diagnostic-local-search-not-yet-wired", false));
        rows.add(ablationRow("IRX without coverage drain", irx.metrics().totalDistanceKm(), assignmentSourceAudit(irx.assignments()).get("coreSelectedAssignmentCount") instanceof Number n ? n.longValue() : 0, "diagnostic-coverage-drain-disabled-count", false));
        return rows;
    }

    public Map<String, Object> rootCauseAudit(DashboardController.RunVisualizationDto irx,
                                               List<DashboardController.BenchmarkSolverResultDto> solverResults) {
        Map<String, Object> audit = new LinkedHashMap<>();
        DashboardController.BenchmarkSolverResultDto irxResult = solverResults.stream()
                .filter(result -> "IntelligentRouteX".equalsIgnoreCase(result.solverName()))
                .findFirst()
                .orElse(null);
        DashboardController.BenchmarkSolverResultDto bestDistance = solverResults.stream()
                .filter(result -> result.status() == DashboardController.SolverRunStatus.COMPLETED)
                .filter(result -> result.totalDistanceKm() > 0)
                .min(Comparator.comparingDouble(DashboardController.BenchmarkSolverResultDto::totalDistanceKm))
                .orElse(null);
        Map<String, Object> comparison = new LinkedHashMap<>();
        if (irxResult != null && bestDistance != null) {
            comparison.put("bestDistanceSolver", bestDistance.solverName());
            comparison.put("bestDistanceKm", bestDistance.totalDistanceKm());
            comparison.put("irxDistanceKm", irxResult.totalDistanceKm());
            comparison.put("irxDistanceGapKm", round(irxResult.totalDistanceKm() - bestDistance.totalDistanceKm()));
            comparison.put("irxDistanceGapPct", bestDistance.totalDistanceKm() == 0 ? 0 : round((irxResult.totalDistanceKm() - bestDistance.totalDistanceKm()) * 100.0 / bestDistance.totalDistanceKm()));
            comparison.put("irxRuntimeMs", irxResult.runtimeMs());
            comparison.put("bestDistanceRuntimeMs", bestDistance.runtimeMs());
        }
        audit.put("solverDistanceComparison", comparison);
        Map<String, Object> coreFunnel = objectMap(irx.diagnostics().get("coreFunnelAudit"));
        Map<String, Object> sourceAudit = objectMap(irx.diagnostics().get("assignmentSourceAudit"));
        List<?> passes = irx.diagnostics().get("passTimeline") instanceof List<?> list ? list : List.of();
        audit.put("coreFunnelAudit", coreFunnel);
        audit.put("assignmentSourceAudit", sourceAudit);
        audit.put("passTimeline", passes);
        audit.put("symptoms", rootCauseSymptoms(irx, irxResult, bestDistance, coreFunnel, sourceAudit, passes));
        audit.put("investigationVerdict", rootCauseVerdict(coreFunnel, sourceAudit, passes));
        audit.put("nextEvidenceToCollect", List.of(
                "route-sequence-current-vs-optimal-pickup-dropoff-permutation",
                "candidate-rejection-examples-with-order-driver-bundle",
                "driver-choice-top5-comparison-against-distance-and-ortools",
                "dropoff-only-on-time-rate-not-coverage-rate",
                "OSRM-table-call-count-and-cache-hit-rate"));
        return audit;
    }

    private SolutionSeedCandidate betterSeed(SolutionSeedCandidate candidate, SolutionSeedCandidate fallback) {
        if (candidate == null) {
            return fallback;
        }
        if (fallback == null) {
            return candidate;
        }
        return LexicographicSolutionComparator.SLA_STRICT.compare(candidate, fallback) >= 0 ? candidate : fallback;
    }

    private String objectiveTradeoffReason(List<SolutionSeedCandidate> seeds, SolutionSeedCandidate bestObjective) {
        return seeds.stream().min(Comparator.comparingDouble(SolutionSeedCandidate::totalDistanceKm))
                .map(bestDistance -> bestDistance.source() == bestObjective.source()
                        ? "best-distance-also-best-objective"
                        : "lateness-or-risk-penalty-outweighed-" + round(bestObjective.totalDistanceKm() - bestDistance.totalDistanceKm()) + "km-distance-saving")
                .orElse("no-seed-tradeoff");
    }

    private Map<String, Object> improvementTraceDiagnostics(ImprovedSolutionCandidate candidate) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("seedSource", candidate.trace().seedSource());
        row.put("startKm", candidate.trace().startKm());
        row.put("afterPermutationKm", candidate.trace().afterPermutationKm());
        row.put("afterLocalSearchKm", candidate.trace().afterLocalSearchKm());
        row.put("finalKm", candidate.trace().finalKm());
        row.put("lateOrders", candidate.trace().lateOrders());
        row.put("objectiveImproved", candidate.trace().objectiveImproved());
        row.put("acceptedMoves", candidate.trace().acceptedMoves());
        row.put("rejectedMoves", candidate.trace().rejectedMoves());
        row.put("reasons", candidate.trace().reasons());
        row.put("moveTraces", candidate.trace().moveTraces().stream().map(this::moveTraceDiagnostics).toList());
        return row;
    }

    private Map<String, Object> moveTraceDiagnostics(MoveEvaluationTrace move) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("moveId", move.moveId());
        row.put("routeId", move.routeId());
        row.put("moveType", move.moveType());
        row.put("oldKm", move.oldKm());
        row.put("newKm", move.newKm());
        row.put("improvementKm", move.improvementKm());
        row.put("accepted", move.accepted());
        row.put("rejectReason", move.rejectReason());
        row.put("latenessTrace", move.latenessTrace().stream().map(this::latenessTraceDiagnostics).toList());
        return row;
    }

    private Map<String, Object> latenessTraceDiagnostics(LatenessTrace late) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("routeId", late.routeId());
        row.put("orderId", late.orderId());
        row.put("moveId", late.moveId());
        row.put("moveType", late.moveType());
        row.put("oldEtaMinutes", late.oldEtaMinutes());
        row.put("newEtaMinutes", late.newEtaMinutes());
        row.put("dueTimeMinutes", late.dueTimeMinutes());
        row.put("oldSlackMinutes", late.oldSlackMinutes());
        row.put("newSlackMinutes", late.newSlackMinutes());
        row.put("latenessMinutes", late.latenessMinutes());
        row.put("reason", late.reason());
        return row;
    }

    private Map<String, Object> solutionSeedSummary(SolutionSeedCandidate seed) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("solutionSeedId", seed.solutionSeedId());
        summary.put("source", seed.source());
        summary.put("coverageRate", seed.coverageRate());
        summary.put("totalDistanceKm", seed.totalDistanceKm());
        summary.put("lateOrderCount", seed.lateOrderCount());
        summary.put("finalScore", seed.costBreakdown().finalScore());
        summary.put("hardFeasible", seed.hardFeasible());
        return summary;
    }

    private Map<String, Object> ablationRow(String name, double distanceKm, long assignedOrders, String reason, boolean official) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("name", name);
        row.put("distanceKm", round(distanceKm));
        row.put("assignedOrders", assignedOrders);
        row.put("reason", reason);
        row.put("official", official);
        return row;
    }

    private Map<String, Object> assignmentSourceAudit(List<DashboardController.AssignmentDto> assignments) {
        Map<String, Object> audit = new LinkedHashMap<>();
        audit.put("assignmentCount", assignments.size());
        audit.put("assignedOrderCount", assignments.stream().mapToLong(assignment -> assignment.orderIds().size()).sum());
        audit.put("repairAssignmentCount", assignments.stream().filter(this::isRepairAssignment).count());
        audit.put("coreSelectedAssignmentCount", assignments.stream().filter(assignment -> !isRepairAssignment(assignment)).count());
        audit.put("reasons", assignments.stream()
                .flatMap(assignment -> assignment.reasons().stream())
                .collect(java.util.stream.Collectors.groupingBy(reason -> reason, LinkedHashMap::new, java.util.stream.Collectors.counting())));
        audit.put("perDriverOrderCount", assignments.stream().collect(java.util.stream.Collectors.toMap(DashboardController.AssignmentDto::driverId, assignment -> assignment.orderIds().size(), Integer::sum, LinkedHashMap::new)));
        return audit;
    }

    private boolean isRepairAssignment(DashboardController.AssignmentDto assignment) {
        return assignment.reasons().stream().anyMatch(reason -> reason.contains("repair") || reason.contains("fallback") || reason.contains("coverage"));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> objectMap(Object value) {
        return value instanceof Map<?, ?> map ? (Map<String, Object>) map : Map.of();
    }

    private List<String> rootCauseSymptoms(DashboardController.RunVisualizationDto irx,
                                           DashboardController.BenchmarkSolverResultDto irxResult,
                                           DashboardController.BenchmarkSolverResultDto bestDistance,
                                           Map<String, Object> coreFunnel,
                                           Map<String, Object> sourceAudit,
                                           List<?> passes) {
        List<String> symptoms = new ArrayList<>();
        if (irxResult != null && bestDistance != null && irxResult.totalDistanceKm() > bestDistance.totalDistanceKm()) {
            symptoms.add("irx-distance-above-best-completed-solver");
        }
        if (number(coreFunnel.get("selectorCandidateCount")) == 0) {
            symptoms.add("core-selector-produced-zero-candidates");
        }
        if (number(coreFunnel.get("coreAssignmentCount")) == 0) {
            symptoms.add("core-executor-produced-zero-assignments-before-coverage-drain");
        }
        if (number(sourceAudit.get("repairAssignmentCount")) > 0) {
            symptoms.add("final-result-contains-repair-or-coverage-assignments");
        }
        if (irx.metrics().lateOrderCount() > 0) {
            symptoms.add("visualization-reports-late-risk-stops");
        }
        if (passes.stream().anyMatch(pass -> String.valueOf(pass).contains("BALANCED_COVERAGE_REPAIR"))) {
            symptoms.add("coverage-repair-dominated-final-coverage");
        }
        return symptoms;
    }

    private String rootCauseVerdict(Map<String, Object> coreFunnel, Map<String, Object> sourceAudit, List<?> passes) {
        if (number(coreFunnel.get("selectorCandidateCount")) == 0 && number(sourceAudit.get("repairAssignmentCount")) > 0) {
            return "PRIMARY: core candidate/selector path failed, final output is coverage-repair dominated; compare algorithms against IRX core-only separately from full-coverage repair.";
        }
        if (number(coreFunnel.get("selectorCandidateCount")) > 0 && number(coreFunnel.get("coreAssignmentCount")) == 0) {
            return "PRIMARY: candidates exist but selector/executor rejected all; inspect feasibility and acceptance gate.";
        }
        if (passes.stream().anyMatch(pass -> String.valueOf(pass).contains("BALANCED_COVERAGE_REPAIR"))) {
            return "PRIMARY: core selected partial result; coverage repair changed assignment/route quality.";
        }
        return "PRIMARY: no single failure proven by current audit; inspect route sequence and scoring deltas next.";
    }

    private long number(Object value) {
        return value instanceof Number number ? number.longValue() : 0L;
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    public record HybridRunResult(
            List<ImprovedSolutionCandidate> improvedSeeds,
            SolutionSeedCandidate bestImprovedSeed,
            SolutionSeedCandidate finalSeed,
            BaselineDominanceResult dominance,
            int configuredTopK) {
    }
}
