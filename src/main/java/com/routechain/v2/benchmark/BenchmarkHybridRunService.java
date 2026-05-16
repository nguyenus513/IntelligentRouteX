package com.routechain.v2.benchmark;

import com.routechain.api.DashboardController;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public final class BenchmarkHybridRunService {
    public DashboardController.RunVisualizationDto run(String jobId,
                                                       DashboardController.BenchmarkJobRequest request,
                                                       BenchmarkRunExecutor executor) {
        return executor.run(jobId, request);
    }

    public Map<String, Object> objectiveAwareDiagnostics(List<DashboardController.BenchmarkSolverResultDto> solverResults) {
        DashboardController.BenchmarkSolverResultDto hybrid = solverResult(solverResults, "IRX ML-Fused Hybrid");
        DashboardController.BenchmarkSolverResultDto distance = solverResult(solverResults, "Distance batching");
        DashboardController.BenchmarkSolverResultDto ortools = solverResult(solverResults, "OR-Tools");
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        String vsDistance = compareRawKm(hybrid, distance);
        String vsOrtools = compareRawKm(hybrid, ortools);
        String vsDistanceObjective = compareObjective(hybrid, distance);
        String vsOrtoolsObjective = compareObjective(hybrid, ortools);
        diagnostics.put("vsDistance", vsDistance);
        diagnostics.put("vsOrtools", vsOrtools);
        diagnostics.put("vsDistanceObjective", vsDistanceObjective);
        diagnostics.put("vsOrtoolsObjective", vsOrtoolsObjective);
        diagnostics.put("hybridLateAdjustedKm", lateAdjustedKm(hybrid));
        diagnostics.put("distanceLateAdjustedKm", lateAdjustedKm(distance));
        diagnostics.put("ortoolsLateAdjustedKm", lateAdjustedKm(ortools));
        diagnostics.put("distanceTradeoffReason", distanceTradeoffReason(hybrid, distance, vsDistance));
        diagnostics.put("distanceObjectiveSummary", singleResultSummary(vsDistanceObjective));
        diagnostics.put("ortoolsObjectiveSummary", singleResultSummary(vsOrtoolsObjective));
        diagnostics.put("rawDistanceWinThresholdPassed", "WIN".equals(vsDistance));
        diagnostics.put("objectiveDistanceWinTieThresholdPassed", isWinOrTie(vsDistanceObjective));
        diagnostics.put("objectiveOrtoolsWinTieThresholdPassed", isWinOrTie(vsOrtoolsObjective));
        diagnostics.put("objectiveAwareBenchmarkSummary", Map.of(
                "distanceObjectiveSummary", diagnostics.get("distanceObjectiveSummary"),
                "ortoolsObjectiveSummary", diagnostics.get("ortoolsObjectiveSummary"),
                "distanceTradeoffReason", diagnostics.get("distanceTradeoffReason")));
        return diagnostics;
    }

    @FunctionalInterface
    public interface BenchmarkRunExecutor {
        DashboardController.RunVisualizationDto run(String jobId, DashboardController.BenchmarkJobRequest request);
    }

    private DashboardController.BenchmarkSolverResultDto solverResult(List<DashboardController.BenchmarkSolverResultDto> solverResults, String solverName) {
        return solverResults.stream()
                .filter(result -> solverName.equals(result.solverName()))
                .findFirst()
                .orElse(null);
    }

    private String compareRawKm(DashboardController.BenchmarkSolverResultDto left, DashboardController.BenchmarkSolverResultDto right) {
        if (left == null || right == null || left.status() != DashboardController.SolverRunStatus.COMPLETED || right.status() != DashboardController.SolverRunStatus.COMPLETED) {
            return "EVIDENCE_GAP";
        }
        if (left.totalDistanceKm() < right.totalDistanceKm()) {
            return "WIN";
        }
        if (Double.compare(left.totalDistanceKm(), right.totalDistanceKm()) == 0) {
            return "TIE";
        }
        return "LOSS";
    }

    private String compareObjective(DashboardController.BenchmarkSolverResultDto left, DashboardController.BenchmarkSolverResultDto right) {
        if (left == null || right == null || left.status() != DashboardController.SolverRunStatus.COMPLETED || right.status() != DashboardController.SolverRunStatus.COMPLETED) {
            return "EVIDENCE_GAP";
        }
        if (left.lateOrderCount() < right.lateOrderCount()) {
            return "WIN";
        }
        if (left.lateOrderCount() > right.lateOrderCount()) {
            return "LOSS";
        }
        return compareRawKm(left, right);
    }

    private double lateAdjustedKm(DashboardController.BenchmarkSolverResultDto result) {
        if (result == null || result.status() != DashboardController.SolverRunStatus.COMPLETED) {
            return 0.0;
        }
        return Math.round((result.totalDistanceKm() + result.lateOrderCount() * 25.0) * 10.0) / 10.0;
    }

    private String distanceTradeoffReason(DashboardController.BenchmarkSolverResultDto hybrid,
                                          DashboardController.BenchmarkSolverResultDto distance,
                                          String vsDistance) {
        if (hybrid == null || distance == null) {
            return "baseline-distance-unavailable";
        }
        if ("LOSS".equals(vsDistance) && distance.lateOrderCount() > hybrid.lateOrderCount()) {
            return "baseline-distance-is-shorter-but-late";
        }
        if ("LOSS".equals(vsDistance)) {
            return "baseline-distance-is-shorter-same-or-better-late";
        }
        return "irx-raw-distance-win-or-tie";
    }

    private Map<String, Object> singleResultSummary(String result) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("win", "WIN".equals(result) ? 1 : 0);
        summary.put("tie", "TIE".equals(result) ? 1 : 0);
        summary.put("loss", "LOSS".equals(result) ? 1 : 0);
        return summary;
    }

    private boolean isWinOrTie(String result) {
        return "WIN".equals(result) || "TIE".equals(result);
    }
}
